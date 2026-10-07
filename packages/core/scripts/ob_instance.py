#!/usr/bin/env python3
"""
ob_instance.py — manage onboarded *instances*: one tenant + the client repos it
describes + its own Postgres database + its own shell environment.

    instance = tenant (domain.json, templates, tickets)
             + workspace (cloned client repos at pinned commits, runs, notes)
             + database  (ob_<slug> on the shared local Postgres)
             + env file  (~/.onboarded/instances/<slug>.env)
             + manifest  (instances/<slug>/instance.json) and SCORECARD.md

Where things live
-----------------
    repo (committed for PUBLIC instances only)
        instances/<slug>/instance.json, SCORECARD.md, FINDINGS.md
        packages/core/tenants/<slug>/          domain.json, scripts/<ticket>/
        templates/<slug>/                      sql templates + scaffolds
        packages/core/generated/<slug>/        (generated)
        packages/shared/src/lib/tenants/<slug>.ts   (generated)
    workspace  ($OB_WORKSPACE, default ~/onboarded-workspace — never committed)
        <slug>/repos/<dir>/                    client clones
        <slug>/runs/  <slug>/notes/  <slug>/dumps/
        <slug>/overlay/{instance,tenant,templates}/   CONFIDENTIAL instances only;
                                               symlinked into the repo paths above
                                               and hidden via .git/info/exclude

Commands
--------
    new <slug> --name N --industry I [--repo URL[@REF] ...] [--confidential]
    adopt <slug> [--confidential]      register an existing tenant (e.g. msi)
    list | show <slug>
    clone <slug> [--full]              clone/update repos; pins commits first time
    pin <slug>                         record each repo's current HEAD in the manifest
    env <slug> | use <slug>            write env file / make it the active instance
    pgpass                             write ~/.pgpass entries from deploy/local/db/.env
    db-create <slug> | db-drop <slug> --yes | db-load <slug> FILE
    generate <slug>                    validate + generate adapters
    check-paths <slug>                 every REPO:path in domain.json exists in the clones?
    doctor [<slug>]                    end-to-end health check
    status <slug> <state>              planned|cloned|derived|generated|benchmarked|archived
    guard                              install pre-commit hook that blocks confidential paths

Stdlib only (Python >= 3.10). Needs git; psql (host) or docker for db-*.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(os.environ.get("ONBOARDED_DIR") or Path(__file__).resolve().parents[3])
WORKSPACE = Path(os.environ.get("OB_WORKSPACE") or Path.home() / "onboarded-workspace").expanduser()
ENV_DIR = Path.home() / ".onboarded" / "instances"
ACTIVE_FILE = Path.home() / ".onboarded" / "active"
DB_SQL_DIR = REPO_ROOT / "deploy" / "local" / "db" / "sql"
DB_ENV_FILE = REPO_ROOT / "deploy" / "local" / "db" / ".env"
PG_CONTAINER = os.environ.get("OB_PG_CONTAINER", "onboarded-pg")

STATES = ("planned", "cloned", "derived", "generated", "benchmarked", "archived")
SLUG_RE = re.compile(r"^[a-z][a-z0-9_]{1,30}$")
EXCLUDE_BEGIN, EXCLUDE_END = "# >>> ob-instance confidential (managed) >>>", "# <<< ob-instance confidential <<<"


# ── paths ────────────────────────────────────────────────────────────────────
def repo_paths(slug: str) -> dict[str, Path]:
    return {
        "instance": REPO_ROOT / "instances" / slug,
        "tenant": REPO_ROOT / "packages" / "core" / "tenants" / slug,
        "templates": REPO_ROOT / "templates" / slug,
    }


def generated_paths(slug: str) -> list[Path]:
    return [
        REPO_ROOT / "packages" / "core" / "generated" / slug,
        REPO_ROOT / "packages" / "shared" / "src" / "lib" / "tenants" / f"{slug}.ts",
        REPO_ROOT / "packages" / "portal" / "src" / "types" / "lib" / "tenants" / f"{slug}.ts",
    ]


def ws(slug: str) -> Path:
    return WORKSPACE / slug


def manifest_path(slug: str) -> Path:
    return repo_paths(slug)["instance"] / "instance.json"


def load(slug: str) -> dict:
    p = manifest_path(slug)
    if not p.is_file():
        die(f"No instance '{slug}'. Create it: ob-instance new {slug} ...  (or adopt an existing tenant)")
    return json.loads(p.read_text())


def save(m: dict) -> None:
    m["updated"] = now()
    p = manifest_path(m["slug"])
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(m, indent=2) + "\n")


def all_slugs() -> list[str]:
    root = REPO_ROOT / "instances"
    return sorted(p.name for p in root.iterdir() if (p / "instance.json").is_file()) if root.is_dir() else []


# ── helpers ──────────────────────────────────────────────────────────────────
def now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def die(msg: str, code: int = 1):
    print(f"✖ {msg}", file=sys.stderr)
    sys.exit(code)


def ok(msg: str) -> None:
    print(f"  ✔ {msg}")


def warn(msg: str) -> None:
    print(f"  ⚠ {msg}")


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, text=True, capture_output=True, **kw)


def env_var_for(slug: str, key: str) -> str:
    return re.sub(r"[^A-Z0-9]", "_", f"{slug}_REPO_{key}".upper())


def parse_repo_arg(spec: str) -> dict:
    """URL[@REF]  →  {key, url, ref, dir, commit}. The ref is whatever follows
    an '@' in the last path segment, so git@host:org/repo.git still parses."""
    head, _, last = spec.rstrip("/").rpartition("/")
    ref = None
    if "@" in last:
        last, ref = last.split("@", 1)
    url = f"{head}/{last}" if head else last
    name = re.sub(r"\.git$", "", last)
    return {"key": name, "url": url, "ref": ref or None, "dir": name, "commit": None}


def db_name(slug: str) -> str:
    return f"ob_{slug}"


# ── confidential overlay ─────────────────────────────────────────────────────
def _git_dir() -> Path | None:
    r = run(["git", "-C", str(REPO_ROOT), "rev-parse", "--git-dir"])
    return (REPO_ROOT / r.stdout.strip()).resolve() if r.returncode == 0 else None


def confidential_slugs() -> list[str]:
    out = []
    for s in all_slugs():
        try:
            if json.loads(manifest_path(s).read_text()).get("classification") == "confidential":
                out.append(s)
        except Exception:
            pass
    return out


def exclude_patterns(slug: str) -> list[str]:
    rel = lambda p: "/" + str(p.relative_to(REPO_ROOT))
    return [rel(p) for p in repo_paths(slug).values()] + [rel(p) for p in generated_paths(slug)]


def sync_git_exclude() -> None:
    gd = _git_dir()
    if not gd:
        return
    ex = gd / "info" / "exclude"
    ex.parent.mkdir(parents=True, exist_ok=True)
    text = ex.read_text() if ex.exists() else ""
    text = re.sub(re.escape(EXCLUDE_BEGIN) + r".*?" + re.escape(EXCLUDE_END) + r"\n?", "", text, flags=re.S)
    pats = [p for s in confidential_slugs() for p in exclude_patterns(s)]
    if pats:
        text = text.rstrip("\n") + "\n" + EXCLUDE_BEGIN + "\n" + "\n".join(pats) + "\n" + EXCLUDE_END + "\n"
    ex.write_text(text)


def link_overlay(slug: str) -> None:
    """Move the instance/tenant/templates dirs into the workspace overlay and symlink them back."""
    for name, repo_p in repo_paths(slug).items():
        target = ws(slug) / "overlay" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if repo_p.is_symlink():
            continue
        if repo_p.exists():
            if target.exists():
                die(f"Both {repo_p} and {target} exist — resolve by hand.")
            shutil.move(str(repo_p), str(target))
        else:
            target.mkdir(parents=True, exist_ok=True)
        repo_p.parent.mkdir(parents=True, exist_ok=True)
        repo_p.symlink_to(target, target_is_directory=True)


# ── commands ─────────────────────────────────────────────────────────────────
SCORECARD = """# Scorecard — {name} (`{slug}`)

Industry: {industry} · Classification: {classification} · Created: {created}

Fill this in as you go; `ob-instance doctor {slug}` fills nothing in for you.

## 1. Derivation (docs/development/derivation.md steps 1–11)
| Step | Done | Time spent | Notes |
|---|---|---|---|
| Repos + config.repos | | | |
| Operations (business flows → controllers/services) | | | |
| Statuses (from DB enum / code enum) | | | |
| Glossary | | | |
| Scan rules | | | |
| DB: schema, sql_templates, clusters, policy_config | | | |
| Validate + generate | | | |

## 2. Coverage (re-run after every repo update)
| Metric | Value |
|---|---|
| Operations defined | |
| `check-paths` resolved / total | |
| Statuses mapped | |
| Scan rules / findings / false positives | |
| Tables profiled (schema) | |
| Error clusters defined | |

## 3. Benchmark — question → answer, onboarded vs. grep/IDE baseline
| # | Question a new engineer would ask | Baseline (min) | onboarded (min) | Correct? |
|---|---|---|---|---|
| 1 | | | | |

## 4. DBA rehearsal
| Ticket | Scenario | diagnostic | dryrun gates | fix --sandbox | fix live | rollback |
|---|---|---|---|---|---|---|

## 5. Engine gaps found (things the engine could not express for this codebase)
-
"""


def cmd_new(a) -> None:
    slug = a.slug
    if not SLUG_RE.match(slug):
        die("slug must be lowercase letters/digits/underscore, start with a letter, ≤31 chars")
    if manifest_path(slug).exists() or repo_paths(slug)["tenant"].exists():
        die(f"'{slug}' already exists (use adopt for an existing tenant)")
    repos = [parse_repo_arg(r) for r in a.repo]
    m = {
        "slug": slug, "name": a.name or slug, "industry": a.industry or "",
        "classification": "confidential" if a.confidential else "public",
        "status": "planned", "created": now(),
        "repos": repos,
        "db": {"dialect": a.dialect, "name": db_name(slug), "source": ""},
        "notes": "",
    }
    if a.confidential:
        save(m)                    # write into repo path first, then move into overlay
        link_overlay(slug)
        sync_git_exclude()
    save(m)

    # tenant domain.json from the generic template
    generic = json.loads((REPO_ROOT / "packages/core/tenants/generic/domain/domain.json").read_text())
    dom = dict(generic)
    dom["tenant"] = {**generic["tenant"], "slug": slug, "brand_name": a.name or slug, "cli_name": a.cli or "ob"}
    dom["config"] = {"repos": {r["key"]: {"env": env_var_for(slug, r["key"]), "default": r["dir"]} for r in repos}}
    dom["db_schema"] = {"dialect": a.dialect, "database": db_name(slug)}
    tdir = repo_paths(slug)["tenant"] / "domain"
    tdir.mkdir(parents=True, exist_ok=True)
    (tdir / "domain.json").write_text(json.dumps(dom, indent=2, ensure_ascii=False) + "\n")
    (repo_paths(slug)["tenant"] / "scripts").mkdir(exist_ok=True)

    # templates: copy generic scaffolds + schema probe as a starting point
    src = REPO_ROOT / "templates" / "generic"
    dst = repo_paths(slug)["templates"]
    if src.is_dir():
        shutil.copytree(src, dst, dirs_exist_ok=True)

    inst = repo_paths(slug)["instance"]
    (inst / "SCORECARD.md").write_text(SCORECARD.format(**m))
    (inst / "FINDINGS.md").write_text(f"# Findings — {m['name']}\n\n<!-- dated, one per line: what onboarded got right/wrong -->\n")
    for d in ("repos", "runs", "notes", "dumps"):
        (ws(slug) / d).mkdir(parents=True, exist_ok=True)
    write_env(m)
    print(f"Created instance '{slug}' ({m['classification']}).")
    ok(f"manifest   {manifest_path(slug)}")
    ok(f"tenant     {repo_paths(slug)['tenant']}/domain/domain.json  (copied from generic — derive it)")
    ok(f"workspace  {ws(slug)}")
    ok(f"env        {ENV_DIR / (slug + '.env')}")
    print(f"Next: ob-instance clone {slug} && ob-instance db-create {slug}")


def cmd_adopt(a) -> None:
    slug = a.slug
    if not repo_paths(slug)["tenant"].is_dir():
        die(f"No tenant at {repo_paths(slug)['tenant']}")
    if manifest_path(slug).exists():
        die(f"'{slug}' is already an instance")
    dom = json.loads((repo_paths(slug)["tenant"] / "domain" / "domain.json").read_text())
    repos = [{"key": k, "url": None, "ref": None, "dir": v.get("default", k), "commit": None}
             for k, v in (dom.get("config", {}).get("repos") or {}).items()]
    m = {"slug": slug, "name": dom.get("tenant", {}).get("brand_name", slug), "industry": a.industry or "",
         "classification": "confidential" if a.confidential else "public", "status": "derived",
         "created": now(), "repos": repos,
         "db": {"dialect": (dom.get("db_schema") or {}).get("dialect", a.dialect), "name": db_name(slug), "source": ""},
         "notes": "adopted existing tenant"}
    save(m)
    if a.confidential:
        sync_git_exclude()
        tracked = run(["git", "-C", str(REPO_ROOT), "ls-files", str(repo_paths(slug)["tenant"])]).stdout.strip()
        if tracked:
            warn(f"{slug} is CONFIDENTIAL but its tenant files are already tracked by git.")
            warn("Exclude rules do not untrack files. When you are ready:")
            print(f"      git rm -r --cached packages/core/tenants/{slug} templates/{slug} "
                  f"packages/core/generated/{slug}\n      ob-instance overlay {slug}   # move into the workspace + symlink")
            warn("Earlier commits still contain them; rewriting history is a separate decision.")
    for d in ("repos", "runs", "notes", "dumps"):
        (ws(slug) / d).mkdir(parents=True, exist_ok=True)
    write_env(m)
    print(f"Adopted '{slug}'. Edit repo dirs/urls in {manifest_path(slug)} if needed.")


def cmd_overlay(a) -> None:
    m = load(a.slug)
    if m["classification"] != "confidential":
        die("overlay is only for confidential instances")
    link_overlay(a.slug)
    sync_git_exclude()
    ok(f"{a.slug} now lives in {ws(a.slug) / 'overlay'} (symlinked into the repo, git-excluded)")


def cmd_list(a) -> None:
    rows = []
    for s in all_slugs():
        m = json.loads(manifest_path(s).read_text())
        cloned = sum((ws(s) / "repos" / r["dir"] / ".git").exists() for r in m["repos"])
        rows.append((s, m.get("industry", ""), m["classification"], m["status"],
                     f"{cloned}/{len(m['repos'])}", m["db"]["name"]))
    active = ACTIVE_FILE.read_text().strip() if ACTIVE_FILE.exists() else ""
    hdr = ("slug", "industry", "class", "status", "repos", "database")
    w = [max(len(h), *(len(r[i]) for r in rows)) if rows else len(h) for i, h in enumerate(hdr)]
    print("  " + "  ".join(h.ljust(w[i]) for i, h in enumerate(hdr)))
    for r in rows:
        mark = "▶" if r[0] == active else " "
        print(mark + " " + "  ".join(c.ljust(w[i]) for i, c in enumerate(r)))


def cmd_show(a) -> None:
    print(json.dumps(load(a.slug), indent=2))


def _head(path: Path) -> str | None:
    r = run(["git", "-C", str(path), "rev-parse", "HEAD"])
    return r.stdout.strip() if r.returncode == 0 else None


def cmd_clone(a) -> None:
    m = load(a.slug)
    for r in m["repos"]:
        if not r.get("url"):
            warn(f"{r['key']}: no url in manifest — skipped"); continue
        dest = ws(a.slug) / "repos" / r["dir"]
        if (dest / ".git").exists():
            run(["git", "-C", str(dest), "fetch", "--quiet", "origin"])
        else:
            cmd = ["git", "clone", "--quiet"]
            if not a.full:
                cmd += ["--filter=blob:none"]          # full history for the feedback scanner, blobs on demand
            if r.get("ref"):
                cmd += ["--branch", r["ref"]]
            p = run(cmd + [r["url"], str(dest)])
            if p.returncode:
                warn(f"{r['key']}: clone failed: {p.stderr.strip()[:200]}"); continue
        if r.get("commit"):
            p = run(["git", "-C", str(dest), "checkout", "--quiet", "--detach", r["commit"]])
            (ok if p.returncode == 0 else warn)(f"{r['key']} @ {r['commit'][:10]} (pinned)")
        else:
            r["commit"] = _head(dest)
            ok(f"{r['key']} @ {r['commit'][:10]} (pinned now — commit the manifest)")
    if m["status"] == "planned":
        m["status"] = "cloned"
    save(m)


def cmd_pin(a) -> None:
    m = load(a.slug)
    for r in m["repos"]:
        h = _head(ws(a.slug) / "repos" / r["dir"])
        if h:
            r["commit"] = h
            ok(f"{r['key']} @ {h[:10]}")
        else:
            warn(f"{r['key']}: not cloned")
    save(m)


def write_env(m: dict) -> Path:
    slug = m["slug"]
    ENV_DIR.mkdir(parents=True, exist_ok=True)
    port = os.environ.get("OB_DB_PORT") or _db_env().get("OB_DB_PORT") or "55432"
    lines = [
        f"# onboarded instance env — {m['name']} ({slug}). Generated by ob-instance; safe to edit.",
        "# No passwords here: libpq reads them from ~/.pgpass (run: ob-instance pgpass).",
        f"export OB_INSTANCE={slug}",
        f"export OB_TENANT={slug}",
        f"export OB_NAV_SLUG={slug.upper()}",
        f"export OB_WORKSPACE_DIR={ws(slug)}",
        f"export OB_ROOT={ws(slug) / 'repos'}",
        f"export {slug.upper()}_ROOT={ws(slug) / 'repos'}",
    ]
    for r in m["repos"]:
        lines.append(f"export {env_var_for(slug, r['key'])}={ws(slug) / 'repos' / r['dir']}")
    lines += [
        f"export OB_DB_DIALECT={m['db']['dialect']}",
        "export OB_DB_HOST=localhost",
        f"export OB_DB_PORT={port}",
        f"export OB_DB_NAME={m['db']['name']}",
        "export OB_DB_USER=ob_dba",
        f"export OB_DBA_CSV_DIR={ws(slug) / 'runs'}",
    ]
    p = ENV_DIR / f"{slug}.env"
    p.write_text("\n".join(lines) + "\n")
    p.chmod(0o600)
    return p


def cmd_env(a) -> None:
    print(write_env(load(a.slug)))


def cmd_use(a) -> None:
    p = write_env(load(a.slug))
    ACTIVE_FILE.parent.mkdir(parents=True, exist_ok=True)
    ACTIVE_FILE.write_text(a.slug + "\n")
    print(f"Active instance: {a.slug}")
    print(f"In zsh run:  obuse {a.slug}     (or: source {p})")


def _db_env() -> dict:
    out = {}
    if DB_ENV_FILE.is_file():
        for line in DB_ENV_FILE.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def cmd_pgpass(a) -> None:
    e = _db_env()
    if not e:
        die(f"{DB_ENV_FILE} not found — create it from .env.example first")
    port = e.get("OB_DB_PORT", "55432")
    want = {f"localhost:{port}:*:ob_dba": e["OB_DBA_PASSWORD"],
            f"localhost:{port}:*:ob_reader": e["OB_READER_PASSWORD"]}
    pp = Path.home() / ".pgpass"
    lines = pp.read_text().splitlines() if pp.exists() else []
    lines = [l for l in lines if l.rsplit(":", 1)[0] not in want]
    lines += [f"{k}:{v.replace(':', chr(92) + ':')}" for k, v in want.items()]
    pp.write_text("\n".join(lines) + "\n")
    pp.chmod(0o600)
    ok(f"{pp} has ob_dba and ob_reader for localhost:{port}")


def _psql_admin(args: list[str], sql_file: Path | None = None) -> subprocess.CompletedProcess:
    """Run psql as the superuser, via the docker container when it is running, else host psql."""
    if _pg_container_running():
        cmd = ["docker", "exec", "-i", PG_CONTAINER, "psql", "-X", "-q", "-U", "postgres", "-d", "postgres",
               "-v", "ON_ERROR_STOP=1", *args]
        if sql_file:
            cmd += ["-f", f"/bootstrap/{sql_file.name}"]
        return run(cmd)
    if not shutil.which("psql"):
        die("Neither the onboarded-pg container nor a host psql is available.")
    env = dict(os.environ)
    env.setdefault("PGHOST", "localhost")
    env.setdefault("PGPORT", _db_env().get("OB_DB_PORT", "55432"))
    env["PGUSER"] = os.environ.get("OB_PG_ADMIN_USER", "postgres")
    if "POSTGRES_PASSWORD" in _db_env() and "PGPASSWORD" not in os.environ:
        env["PGPASSWORD"] = _db_env()["POSTGRES_PASSWORD"]
    cmd = ["psql", "-X", "-q", "-d", "postgres", "-v", "ON_ERROR_STOP=1", *args]
    if sql_file:
        cmd += ["-f", str(sql_file)]
    return run(cmd, env=env)


def cmd_db_create(a) -> None:
    m = load(a.slug)
    if m["db"]["dialect"] != "postgres":
        die("db-create manages Postgres databases only (this instance is mssql)")
    p = _psql_admin(["-v", f"db_name={m['db']['name']}"], DB_SQL_DIR / "10_instance_db.sql")
    if p.returncode:
        die(p.stderr.strip() or p.stdout.strip())
    ok(f"database {m['db']['name']} ready (owner ob_dba, ob_reader read-only, err.db_exception_tank)")


def cmd_db_drop(a) -> None:
    m = load(a.slug)
    if not a.yes:
        die(f"This deletes database {m['db']['name']}. Re-run with --yes.")
    p = _psql_admin(["-c", f'DROP DATABASE IF EXISTS "{m["db"]["name"]}" WITH (FORCE)'])
    if p.returncode:
        die(p.stderr.strip())
    ok(f"dropped {m['db']['name']}")


def _pg_container_running() -> bool:
    return bool(shutil.which("docker")) and \
        run(["docker", "inspect", "-f", "{{.State.Running}}", PG_CONTAINER]).stdout.strip() == "true"


def cmd_db_load(a) -> None:
    """Load a schema/data dump into the instance DB as ob_dba (so ob_reader grants apply).

    Runs inside the onboarded-pg container when it is up, so pg_restore always
    matches the server version (a dump from a newer Postgres than your host
    client cannot be restored by the older client)."""
    m = load(a.slug)
    f = Path(a.file).expanduser().resolve()
    if not f.is_file():
        die(f"{f} not found")
    custom = f.suffix in (".dump", ".backup") or f.name.endswith(".pgdump")
    dbn = m["db"]["name"]
    if _pg_container_running():
        base = ["docker", "exec", "-i", PG_CONTAINER]
        cmd = base + (["pg_restore", "-U", "ob_dba", "--no-owner", "--role=ob_dba", "-d", dbn]
                      if custom else ["psql", "-X", "-q", "-v", "ON_ERROR_STOP=1", "-U", "ob_dba", "-d", dbn])
        with f.open("rb") as fh:
            p = subprocess.run(cmd, stdin=fh, capture_output=True)
        out, err = p.stdout.decode(errors="replace"), p.stderr.decode(errors="replace")
    else:
        env = dict(os.environ, PGHOST="localhost", PGPORT=_db_env().get("OB_DB_PORT", "55432"),
                   PGUSER="ob_dba", PGDATABASE=dbn)
        cmd = (["pg_restore", "--no-owner", "--role=ob_dba", "-d", dbn, str(f)] if custom
               else ["psql", "-X", "-q", "-v", "ON_ERROR_STOP=1", "-f", str(f)])
        p = run(cmd, env=env)
        out, err = p.stdout, p.stderr
    if p.returncode:
        die((err or out).strip()[-800:])
    m["db"]["source"] = f.name
    save(m)
    ok(f"loaded {f.name} into {dbn}")


def cmd_generate(a) -> None:
    for script in ("validate_domain.py", "generate_adapters.py"):
        p = run([sys.executable, str(REPO_ROOT / "packages/core/scripts" / script), "--tenant", a.slug],
                cwd=REPO_ROOT)
        sys.stdout.write(p.stdout)
        if p.returncode:
            die(f"{script} failed:\n{p.stderr}")
    m = load(a.slug)
    if STATES.index(m["status"]) < STATES.index("generated"):
        m["status"] = "generated"
        save(m)
    if m["classification"] == "confidential":
        sync_git_exclude()


_REF = re.compile(r"^([A-Za-z0-9._-]+):(.+)$")


def iter_path_refs(dom: dict):
    for op, spec in (dom.get("operations") or {}).items():
        for field in ("controllers", "services"):
            for ref in spec.get(field) or []:
                yield f"operations.{op}.{field}", ref
    for t, spec in (dom.get("qe_tests") or {}).items():
        for ref in spec.get("paths") or []:
            yield f"qe_tests.{t}", ref


def cmd_check_paths(a) -> int:
    m = load(a.slug)
    dom = json.loads((repo_paths(a.slug)["tenant"] / "domain" / "domain.json").read_text())
    repos = dom.get("config", {}).get("repos") or {}
    good = bad = 0
    for where, ref in iter_path_refs(dom):
        mm = _REF.match(ref)
        if not mm or mm.group(1) not in repos:
            print(f"  ✖ {where}: '{ref}' — unknown repo key"); bad += 1; continue
        key, rel = mm.groups()
        root = Path(os.environ.get(repos[key].get("env", ""), "") or ws(a.slug) / "repos" / repos[key]["default"])
        if (root / rel).exists():
            good += 1
        else:
            print(f"  ✖ {where}: {ref}"); bad += 1
    total = good + bad
    print(f"  {good}/{total} path references resolve" + ("" if total else " (no references yet)"))
    return 1 if bad else 0


def cmd_doctor(a) -> int:
    slugs = [a.slug] if a.slug else all_slugs()
    problems = 0
    for s in slugs:
        m = load(s)
        print(f"── {s}  ({m['classification']}, {m['status']})")
        dom_p = repo_paths(s)["tenant"] / "domain" / "domain.json"
        if dom_p.is_file():
            ok("domain.json present")
        else:
            warn("domain.json missing"); problems += 1
        gen = REPO_ROOT / "packages/core/generated" / s / "nav_maps.zsh"
        if not gen.is_file():
            warn("adapters not generated — ob-instance generate " + s); problems += 1
        elif dom_p.is_file() and dom_p.stat().st_mtime > gen.stat().st_mtime:
            warn("domain.json is newer than generated adapters — regenerate"); problems += 1
        else:
            ok("adapters up to date")
        for r in m["repos"]:
            d = ws(s) / "repos" / r["dir"]
            h = _head(d)
            if not h:
                warn(f"repo {r['key']} not cloned"); problems += 1
            elif r.get("commit") and h != r["commit"]:
                warn(f"repo {r['key']} at {h[:10]} but manifest pins {r['commit'][:10]}"); problems += 1
            else:
                ok(f"repo {r['key']} @ {h[:10]}")
        if m["db"]["dialect"] == "postgres" and shutil.which("psql"):
            env = dict(os.environ, PGHOST="localhost", PGPORT=_db_env().get("OB_DB_PORT", "55432"),
                       PGUSER="ob_dba", PGDATABASE=m["db"]["name"], PGCONNECT_TIMEOUT="3")
            p = run(["psql", "-X", "-Atc", "select count(*) from err.db_exception_tank"], env=env)
            if p.returncode == 0:
                ok(f"database {m['db']['name']} reachable ({p.stdout.strip()} logged errors)")
            else:
                warn(f"database {m['db']['name']}: {p.stderr.strip().splitlines()[-1] if p.stderr.strip() else 'unreachable'}")
                problems += 1
        if m["classification"] == "confidential":
            leaked = run(["git", "-C", str(REPO_ROOT), "ls-files", "--", *exclude_patterns(s)]).stdout.split()
            leaked = [x for x in leaked if x]
            if leaked:
                warn(f"{len(leaked)} confidential file(s) tracked by git, e.g. {leaked[0]}"); problems += 1
            else:
                ok("no confidential files tracked by git")
            gd = _git_dir()
            ex = (gd / "info" / "exclude").read_text() if gd and (gd / "info" / "exclude").exists() else ""
            if f"/packages/core/tenants/{s}" in ex:
                ok("git exclude rules present")
            else:
                warn("git exclude rules missing — run: ob-instance guard"); problems += 1
    print(f"\n{'✔ healthy' if not problems else f'⚠ {problems} issue(s)'}")
    return 1 if problems else 0


def cmd_status(a) -> None:
    m = load(a.slug)
    m["status"] = a.state
    save(m)
    ok(f"{a.slug} → {a.state}")


HOOK = """#!/usr/bin/env bash
# ob-instance guard: refuse to commit files of CONFIDENTIAL instances (even with git add -f).
exec python3 "$(git rev-parse --show-toplevel)/packages/core/scripts/ob_instance.py" _precommit
"""


def cmd_guard(a) -> None:
    sync_git_exclude()
    gd = _git_dir()
    if not gd:
        die("not a git repository")
    hook = gd / "hooks" / "pre-commit"
    if hook.exists() and "ob-instance guard" not in hook.read_text():
        die(f"{hook} exists and is not ours — add this line to it:\n  python3 packages/core/scripts/ob_instance.py _precommit || exit 1")
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text(HOOK)
    hook.chmod(0o755)
    ok(f"pre-commit guard installed; exclude rules cover {len(confidential_slugs())} confidential instance(s)")


def cmd_precommit(a) -> int:
    staged = run(["git", "-C", str(REPO_ROOT), "diff", "--cached", "--name-only"]).stdout.split()
    pats = [p.lstrip("/") for s in confidential_slugs() for p in exclude_patterns(s)]
    bad = [f for f in staged if any(f == p or f.startswith(p.rstrip("/") + "/") for p in pats)]
    if bad:
        print("✖ ob-instance guard: these files belong to CONFIDENTIAL instances:", file=sys.stderr)
        for f in bad:
            print(f"    {f}", file=sys.stderr)
        print("  Unstage them: git restore --staged <file>", file=sys.stderr)
        return 1
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="ob-instance", description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)

    n = sub.add_parser("new"); n.add_argument("slug")
    n.add_argument("--name"); n.add_argument("--industry"); n.add_argument("--cli")
    n.add_argument("--repo", action="append", default=[], metavar="URL[@REF]")
    n.add_argument("--confidential", action="store_true")
    n.add_argument("--dialect", default="postgres", choices=["postgres", "mssql"])
    ad = sub.add_parser("adopt"); ad.add_argument("slug"); ad.add_argument("--industry")
    ad.add_argument("--confidential", action="store_true")
    ad.add_argument("--dialect", default="postgres", choices=["postgres", "mssql"])
    for name in ("show", "clone", "pin", "env", "use", "db-create", "generate", "check-paths", "overlay"):
        x = sub.add_parser(name); x.add_argument("slug")
        if name == "clone":
            x.add_argument("--full", action="store_true", help="full clone instead of blob-less")
    sub.add_parser("list"); sub.add_parser("pgpass"); sub.add_parser("guard"); sub.add_parser("_precommit")
    dd = sub.add_parser("db-drop"); dd.add_argument("slug"); dd.add_argument("--yes", action="store_true")
    dl = sub.add_parser("db-load"); dl.add_argument("slug"); dl.add_argument("file")
    dr = sub.add_parser("doctor"); dr.add_argument("slug", nargs="?")
    st = sub.add_parser("status"); st.add_argument("slug"); st.add_argument("state", choices=STATES)

    a = p.parse_args(argv)
    fn = {"new": cmd_new, "adopt": cmd_adopt, "overlay": cmd_overlay, "list": cmd_list, "show": cmd_show,
          "clone": cmd_clone, "pin": cmd_pin, "env": cmd_env, "use": cmd_use, "pgpass": cmd_pgpass,
          "db-create": cmd_db_create, "db-drop": cmd_db_drop, "db-load": cmd_db_load,
          "generate": cmd_generate, "check-paths": cmd_check_paths, "doctor": cmd_doctor,
          "status": cmd_status, "guard": cmd_guard, "_precommit": cmd_precommit}[a.cmd]
    rc = fn(a)
    return rc or 0


if __name__ == "__main__":
    sys.exit(main())
