#!/usr/bin/env python3
"""
ob_paths.py — find and repair every path onboarded depends on.

Run it from the checkout you want to use (it locates itself; nothing is
hard-coded). Safe by default: `check` only reads, `fix` prints a plan until
you add --apply, and every file it changes is backed up first.

    ob_paths.py check                      what is stale, and where (exit 1 if anything is)
    ob_paths.py where                      the resolved foundational paths
    ob_paths.py fix [--apply] [options]    repair everything check reports
        --workspace PATH                   where instance workspaces live now
        --msi-nav PATH                     where the msi-nav checkout lives now (optional, legacy)
        --no-msi-nav                       forget msi-nav entirely
        --repos-root PATH                  repos root for non-instance tenants (msi)
        --default-tenant SLUG              tenant loaded when no instance is active
        --from OLD --to NEW                also rewrite this path prefix in shell profiles
    ob_paths.py move-workspace NEW [--apply]   move the workspace directory, then fix
    ob_paths.py env                        `export` lines for the current shell:  eval "$(obpaths env)"
    ob_paths.py backups                    list backups
    ob_paths.py restore <id> [--apply]     put a backup back

What it covers
--------------
  ~/.onboarded/root          symlink to the checkout (the one stable path)
  ~/.onboarded/paths.conf    MSI_NAV_DIR, OB_WORKSPACE, OB_REPOS_ROOT, OB_DEFAULT_TENANT
  shell profiles             ~/.zshrc (or $ZDOTDIR), ~/.zprofile, ~/.zshenv, ~/.bashrc, ~/.bash_profile, ~/.profile:
                             the managed block, the legacy bootstrap block, and any
                             onboarded / msi-nav line whose path no longer exists
  current environment        a stale exported ONBOARDED_DIR / MSI_NAV_DIR / OB_WORKSPACE / OB_ROOT
  instance env files         ~/.onboarded/instances/<slug>.env (regenerated)
  active instance            ~/.onboarded/active
  confidential overlays      repo symlinks into $OB_WORKSPACE/<slug>/overlay (relinked)
  git exclude block          confidential paths in .git/info/exclude (re-synced)
  repo internals             Makefile / justfile / bootstrap.sh self-locate (reported)
  release sync               deploy/local/sync.conf DEST (reported)

Stdlib only, Python >= 3.10.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

HOME = Path.home()
OBH = HOME / ".onboarded"
ROOT_LINK = OBH / "root"
CONF = OBH / "paths.conf"
BACKUPS = OBH / "backups"
REPO = Path(__file__).resolve().parents[3]
DEFAULT_WORKSPACE = HOME / "onboarded"            # instance workspaces (clones, runs, overlays)
LEGACY_WORKSPACE = HOME / "onboarded-workspace"   # name used before 2026-10; still recognised

def workspace_conflict(ws: Path, repo: Path = REPO) -> str | None:
    """The workspace must sit beside the checkout, never on it, in it, or around it."""
    w, r = Path(ws).expanduser().resolve(), repo.resolve()
    if w == r:
        return f"{tilde(w)} is this checkout — the workspace must be a different folder"
    if r in w.parents:
        return f"{tilde(w)} is inside this checkout — client clones would land in the onboarded repo"
    if w in r.parents:
        return f"this checkout is inside {tilde(w)} — move the checkout or pick another workspace"
    return None

def suggest_workspace() -> str:
    """~/onboarded unless that is (or holds) the checkout; then ~/onboarded-instances."""
    return "~/onboarded" if not workspace_conflict(DEFAULT_WORKSPACE) else "~/onboarded-instances"
 
PROFILE_REL = "packages/cli/src/ob_profile.zsh"
DISPATCHER_REL = "packages/cli/src/ob_dispatcher.zsh"

BEGIN, END = "# >>> onboarded >>>", "# <<< onboarded <<<"
MANAGED_BLOCK = (
    f"{BEGIN}\n"
    "# Managed by ob_paths.py. Paths outside the repo live in ~/.onboarded/paths.conf;\n"
    "# ~/.onboarded/root points at the checkout. Repair with: obpaths fix --apply\n"
    '[[ -r "$HOME/.onboarded/root/packages/cli/src/ob_profile.zsh" ]] && \\\n'
    '    source "$HOME/.onboarded/root/packages/cli/src/ob_profile.zsh"\n'
    f"{END}\n"
)
LEGACY_BEGIN = re.compile(r"^# ── Onboarded \((?P<tenant>[^)]*)\) ──\s*$")
LEGACY_END = "# ── /Onboarded ──"
CONF_KEYS = ("MSI_NAV_DIR", "OB_WORKSPACE", "OB_REPOS_ROOT", "OB_DEFAULT_TENANT")
CONF_PATH_KEYS = ("MSI_NAV_DIR", "OB_WORKSPACE", "OB_REPOS_ROOT")
KEYWORDS = re.compile(r"onboarded|ob_dispatcher|ob_profile|ONBOARDED_DIR|OB_ROOT|OB_WORKSPACE|MSI_NAV_DIR|msi[-_]nav",
                      re.IGNORECASE)
PATH_TOKEN = re.compile(r"""(?:~|\$\{?HOME\}?|/)[^\s"'`;:|&)(]*""")
KNOWN_SUFFIXES = (f"/{DISPATCHER_REL}", "/src/ob_dispatcher.zsh", f"/{PROFILE_REL}")


# ── small helpers ────────────────────────────────────────────────────────────
def c(code: str, s: str) -> str:
    return f"\033[{code}m{s}\033[0m" if sys.stdout.isatty() else s


def tilde(p) -> str:
    s = str(p)
    return "~" + s[len(str(HOME)):] if s == str(HOME) or s.startswith(str(HOME) + "/") else s


def expand(tok: str) -> Path | None:
    t = re.sub(r"^(?:~|\$\{HOME\}|\$HOME)", str(HOME), tok)
    if "$" in t or "*" in t:
        return None
    return Path(t)


def rc_files() -> list[Path]:
    zd = Path(os.environ.get("ZDOTDIR") or HOME)
    seen, out = set(), []
    for p in [zd / ".zshrc", zd / ".zprofile", zd / ".zshenv", HOME / ".zshrc",
              HOME / ".bashrc", HOME / ".bash_profile", HOME / ".profile"]:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def primary_rc() -> Path:
    return Path(os.environ.get("ZDOTDIR") or HOME) / ".zshrc"


def read_conf() -> dict:
    out = {}
    if CONF.is_file():
        for line in CONF.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def conf_path(conf: dict, key: str) -> Path | None:
    v = conf.get(key)
    return expand(v) if v else None


def instance_manifests() -> dict[str, dict]:
    out = {}
    d = REPO / "instances"
    if d.is_dir():
        for m in sorted(d.glob("*/instance.json")):
            try:
                out[m.parent.name] = json.loads(m.read_text())
            except Exception:
                pass
    return out


def workspace_now(conf: dict) -> Path:
    return (conf_path(conf, "OB_WORKSPACE") or Path(os.environ.get("OB_WORKSPACE") or DEFAULT_WORKSPACE)).expanduser()


def msi_nav_candidates() -> list[Path]:
    """Bounded search for an msi-nav checkout under $HOME (depth ≤ 4)."""
    hits = []
    skip = {DEFAULT_WORKSPACE, LEGACY_WORKSPACE, workspace_now(read_conf())}   # client clones, not msi-nav
    for base in (HOME, HOME / "develop", HOME / "src", HOME / "code", HOME / "repos", HOME / "work"):
        if not base.is_dir():
            continue
        for root, dirs, _ in os.walk(base):
            depth = Path(root).relative_to(base).parts
            dirs[:] = [d for d in dirs if not d.startswith(".") and d != "node_modules"
                       and Path(root, d) not in skip]
            if len(depth) >= 4:
                dirs[:] = []
            for d in list(dirs):
                if d == "msi-nav" and (Path(root, d) / ".git").exists():
                    p = Path(root, d)
                    if p not in hits:
                        hits.append(p)
    return hits


# ── findings ─────────────────────────────────────────────────────────────────
@dataclass
class Finding:
    area: str
    status: str            # ok | stale | warn | info
    subject: str
    detail: str = ""
    where: str = ""


@dataclass
class Report:
    items: list[Finding] = field(default_factory=list)
    old_roots: set = field(default_factory=set)       # repo roots inferred from stale profile paths
    old_msi: set = field(default_factory=set)         # msi-nav roots inferred from stale profile paths

    def add(self, *a, **kw):
        self.items.append(Finding(*a, **kw))

    @property
    def stale(self):
        return [f for f in self.items if f.status == "stale"]


def scan(report: Report | None = None) -> Report:
    r = report or Report()
    conf = read_conf()

    # 1. checkout + root link
    r.add("repo", "ok", "this checkout", tilde(REPO))
    if ROOT_LINK.is_symlink():
        tgt = Path(os.readlink(ROOT_LINK))
        if not tgt.is_absolute():
            tgt = (ROOT_LINK.parent / tgt)
        if tgt.resolve() == REPO:
            r.add("repo", "ok", "~/.onboarded/root", f"→ {tilde(tgt)}")
        elif not tgt.exists():
            r.add("repo", "stale", "~/.onboarded/root", f"→ {tilde(tgt)} (gone)")
            r.old_roots.add(str(tgt))
        else:
            r.add("repo", "warn", "~/.onboarded/root", f"→ {tilde(tgt)} (another checkout; fix repoints it here)")
    elif ROOT_LINK.exists():
        r.add("repo", "stale", "~/.onboarded/root", "exists but is not a symlink")
    else:
        r.add("repo", "stale", "~/.onboarded/root", "missing")

    # 2. paths.conf
    if not CONF.is_file():
        r.add("conf", "warn", "~/.onboarded/paths.conf", "missing (fix writes it)")
    for k in CONF_PATH_KEYS:
        p = conf_path(conf, k)
        if p is None:
            continue
        r.add("conf", "ok" if p.is_dir() else "stale", k, tilde(p) + ("" if p.is_dir() else " (does not exist)"))
    if conf.get("OB_DEFAULT_TENANT"):
        t = conf["OB_DEFAULT_TENANT"]
        gen = REPO / "packages/core/generated" / t / "nav_maps.zsh"
        r.add("conf", "ok" if gen.is_file() else "stale", "OB_DEFAULT_TENANT",
              t + ("" if gen.is_file() else " (no generated adapters)"))

    # 3. current environment
    od = os.environ.get("ONBOARDED_DIR")
    if od:
        okd = (Path(od) / DISPATCHER_REL).is_file()
        if Path(od).resolve() == REPO:
            r.add("env", "ok", "ONBOARDED_DIR", tilde(od))
        else:
            r.add("env", "warn" if okd else "stale", "ONBOARDED_DIR",
                  f"{tilde(od)} " + ("(another checkout)" if okd else "(not a checkout — open a new shell after fix)"))
            if not okd:
                r.old_roots.add(od)
    for k in ("MSI_NAV_DIR", "OB_WORKSPACE", "OB_ROOT"):
        v = os.environ.get(k)
        if v and not Path(v).expanduser().exists():
            r.add("env", "stale", k, f"{tilde(v)} (exported, does not exist — open a new shell after fix)")

    # 4. shell profiles
    managed_seen = False
    for f in rc_files():
        if not f.is_file():
            continue
        lines = f.read_text(errors="replace").splitlines()
        in_managed = in_legacy = False
        for n, line in enumerate(lines, 1):
            if line.strip() == BEGIN:
                in_managed = managed_seen = True
                continue
            if line.strip() == END:
                in_managed = False
                continue
            if LEGACY_BEGIN.match(line.strip()):
                in_legacy = True
                r.add("profile", "stale", "legacy bootstrap block", "hard-coded paths; fix replaces it", f"{tilde(f)}:{n}")
                continue
            if line.strip() == LEGACY_END:
                in_legacy = False
                continue
            if in_managed or line.lstrip().startswith("#") or not KEYWORDS.search(line):
                continue
            for tok in PATH_TOKEN.findall(line):
                p = expand(tok)
                if p is None or len(str(p)) < 2:
                    continue
                if p.exists():
                    if not in_legacy:
                        r.add("profile", "ok", tilde(p), "", f"{tilde(f)}:{n}")
                else:
                    r.add("profile", "stale", tilde(p), "does not exist", f"{tilde(f)}:{n}")
                    for suf in KNOWN_SUFFIXES:
                        if str(p).endswith(suf):
                            r.old_roots.add(str(p)[: -len(suf)])
                    m = re.match(r"(.*?/msi-nav)(?:/|$)", str(p))
                    if m:
                        r.old_msi.add(m.group(1))
    if not managed_seen:
        r.add("profile", "stale", "managed block", f"not in {tilde(primary_rc())} (fix adds it)")

    # 5. instances
    mans = instance_manifests()
    ws = workspace_now(conf)
    envdir = OBH / "instances"
    if envdir.is_dir():
        for ef in sorted(envdir.glob("*.env")):
            slug = ef.stem
            bad, unmade = [], []
            for line in ef.read_text().splitlines():
                m = re.match(r"export ([A-Z0-9_]+)=(.*)$", line.strip())
                if not m:
                    continue
                k, v = m.groups()
                if k in ("OB_WORKSPACE_DIR", "OB_ROOT") or k.endswith("_ROOT"):
                    if not str(Path(v)).startswith(str(ws) + "/"):
                        bad.append(f"{k}={tilde(v)}")          # points outside the current workspace
                    elif not Path(v).exists():
                        unmade.append(k)                       # right place, just not created yet
            if slug not in mans:
                r.add("instance", "warn", f"{slug}.env", "no manifest in this checkout (orphan; left alone)")
            elif bad:
                r.add("instance", "stale", f"{slug}.env", "; ".join(bad[:3]) + (" …" if len(bad) > 3 else ""))
            elif unmade:
                r.add("instance", "warn", f"{slug}.env", "workspace folders not created yet (clone/new creates them)")
            else:
                r.add("instance", "ok", f"{slug}.env", "")
    for slug in mans:
        if not (envdir / f"{slug}.env").is_file():
            r.add("instance", "warn", f"{slug}.env", "missing (fix writes it)")
    act = OBH / "active"
    if act.is_file():
        slug = act.read_text().strip()
        r.add("instance", "ok" if slug in mans else "stale", "~/.onboarded/active",
              slug + ("" if slug in mans else " (no such instance here)"))
    if mans and not ws.is_dir():
        r.add("instance", "warn", "OB_WORKSPACE", f"{tilde(ws)} does not exist (clone/new will create it)")

    if (why := workspace_conflict(ws)):
        r.add("instance", "stale", "OB_WORKSPACE", why + f"; fix with: obpaths fix --workspace {suggest_workspace()} --apply")
    elif ws.resolve() == LEGACY_WORKSPACE.resolve():
        r.add("instance", "warn", "OB_WORKSPACE",
              f"{tilde(ws)} is the old default name; to rename: obpaths move-workspace {suggest_workspace()} --apply")
    elif LEGACY_WORKSPACE.is_dir() and any(LEGACY_WORKSPACE.iterdir()):
        r.add("instance", "warn", "OB_WORKSPACE",
              f"{tilde(LEGACY_WORKSPACE)} still exists and is not in use (move what you need into {tilde(ws)}, then delete it)")

    # 6. confidential overlays
    for kind, base in (("instance", REPO / "instances"), ("tenant", REPO / "packages/core/tenants"),
                       ("templates", REPO / "templates")):
        if not base.is_dir():
            continue
        for p in sorted(base.iterdir()):
            if p.is_symlink():
                tgt = Path(os.readlink(p))
                if tgt.exists():
                    r.add("overlay", "ok", str(p.relative_to(REPO)), f"→ {tilde(tgt)}")
                else:
                    want = ws / p.name / "overlay" / kind
                    r.add("overlay", "stale", str(p.relative_to(REPO)),
                          f"→ {tilde(tgt)} (gone)" + (f"; will relink to {tilde(want)}" if want.exists() else "; no overlay found in workspace"))

    # 7. msi-nav
    # msi-nav is an optional legacy reference: only checked when configured.
    mn = conf_path(conf, "MSI_NAV_DIR") or (Path(os.environ["MSI_NAV_DIR"]) if os.environ.get("MSI_NAV_DIR") else None)
    if mn is None:
        r.add("msi-nav", "info", "MSI_NAV_DIR", "not configured (optional legacy reference; not used by onboarded)")
    elif mn.is_dir():
        r.add("msi-nav", "ok", "MSI_NAV_DIR", tilde(mn) + " (legacy reference)")
    else:
        r.add("msi-nav", "stale", "MSI_NAV_DIR", f"{tilde(mn)} does not exist (fix --msi-nav PATH, or fix --no-msi-nav)")

    # 8. repo internals
    mk = (REPO / "Makefile").read_text() if (REPO / "Makefile").is_file() else ""
    jf = (REPO / "justfile").read_text() if (REPO / "justfile").is_file() else ""
    bs = (REPO / "packages/core/scripts/bootstrap.sh")
    r.add("repo", "ok" if "abspath $(lastword $(MAKEFILE_LIST))" in mk else "stale", "Makefile ONBOARDED_DIR",
          "self-locating" if "abspath $(lastword" in mk else "hard-coded default (apply the patch)")
    r.add("repo", "ok" if "justfile_directory()" in jf else "stale", "justfile ONBOARDED_DIR",
          "self-locating" if "justfile_directory()" in jf else "hard-coded default (apply the patch)")
    if bs.is_file():
        legacy = "ob_paths.py" not in bs.read_text()
        r.add("repo", "stale" if legacy else "ok", "bootstrap.sh profile block",
              "injects the old /src/ob_dispatcher.zsh path" if legacy else "delegates to ob_paths.py")

    # 9. release sync destination (informational)
    sc = REPO / "deploy/local/sync.conf"
    if sc.is_file():
        m = re.search(r"^DEST=(.*)$", sc.read_text(), re.M)
        if m:
            d = expand(m.group(1).strip())
            if d is not None:
                r.add("sync", "info" if d.parent.is_dir() else "warn", "sync.conf DEST",
                      tilde(d) + ("" if d.parent.is_dir() else " (parent missing)"))
    return r


def print_report(r: Report) -> int:
    icon = {"ok": c("32", "✔"), "stale": c("31", "✖"), "warn": c("33", "⚠"), "info": c("36", "ℹ")}
    area = None
    for f in r.items:
        if f.area != area:
            area = f.area
            print(c("1", f"\n── {area}"))
        where = c("2", f"  [{f.where}]") if f.where else ""
        print(f"  {icon[f.status]} {f.subject}" + (f"  {f.detail}" if f.detail else "") + where)
    n = len(r.stale)
    warns = sum(1 for f in r.items if f.status == "warn")
    print()
    if n:
        print(c("31", f"✖ {n} stale path(s), {warns} warning(s).") + " Preview the repair: ob_paths.py fix   then: ob_paths.py fix --apply")
        if r.old_roots:
            print(c("2", "  old checkout location(s) seen: " + ", ".join(sorted(tilde(x) for x in r.old_roots))))
    else:
        print(c("32", f"✔ all paths resolve ({warns} warning(s))."))
    return 1 if n else 0


# ── backups ──────────────────────────────────────────────────────────────────
class Backup:
    def __init__(self, apply: bool):
        self.apply = apply
        self.id = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        self.dir = BACKUPS / self.id
        self.meta = {"files": {}, "links": {}, "new_files": [], "created": self.id, "repo": str(REPO)}

    def file(self, p: Path):
        if not self.apply or str(p) in self.meta["files"]:
            return
        if not p.exists():
            if str(p) not in self.meta["new_files"]:
                self.meta["new_files"].append(str(p))       # restore deletes it
            return
        (self.dir / "files").mkdir(parents=True, exist_ok=True)
        name = str(p).replace("/", "%")
        shutil.copy2(p, self.dir / "files" / name)
        self.meta["files"][str(p)] = name

    def link(self, p: Path):
        if not self.apply or str(p) in self.meta["links"]:
            return
        self.meta["links"][str(p)] = os.readlink(p) if p.is_symlink() else None

    def close(self):
        if self.apply and (self.meta["files"] or self.meta["links"] or self.meta["new_files"]):
            self.dir.mkdir(parents=True, exist_ok=True)
            (self.dir / "manifest.json").write_text(json.dumps(self.meta, indent=2))
            return self.id
        return None


# ── fix ──────────────────────────────────────────────────────────────────────
def _write(path: Path, text: str, bk: Backup, apply: bool, plan: list, why: str):
    old = path.read_text() if path.is_file() else None
    if old == text:
        return
    plan.append(f"write {tilde(path)}  — {why}")
    if apply:
        bk.file(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)


def _symlink(path: Path, target: Path, bk: Backup, apply: bool, plan: list, why: str):
    if path.is_symlink() and Path(os.readlink(path)) == target:
        return
    plan.append(f"link  {tilde(path)} → {tilde(target)}  — {why}")
    if apply:
        bk.link(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.is_symlink() or path.is_file():
            path.unlink()
        elif path.exists():
            raise SystemExit(f"✖ {path} is a real directory; move it aside first")
        path.symlink_to(target, target_is_directory=True)


def _legacy_values() -> dict:
    """Carry OB_ROOT / OB_TENANT over from a legacy bootstrap block."""
    out = {}
    for f in rc_files():
        if not f.is_file():
            continue
        in_legacy = False
        for line in f.read_text(errors="replace").splitlines():
            s = line.strip()
            if LEGACY_BEGIN.match(s):
                in_legacy = True
                continue
            if s == LEGACY_END:
                in_legacy = False
                continue
            if in_legacy:
                m = re.match(r'export (OB_ROOT|OB_TENANT)="?([^"]*)"?$', s)
                if m:
                    out[m.group(1)] = m.group(2)
    return out


def rewrite_profile(text: str, prefix_map: list[tuple[str, str]], stamp: str, add_block: bool) -> str:
    out, in_legacy, in_managed, had_block = [], False, False, False
    for line in text.splitlines():
        s = line.strip()
        if s == BEGIN:
            in_managed = had_block = True
            continue
        if s == END:
            in_managed = False
            continue
        if in_managed:
            continue                                  # re-emitted fresh below
        if LEGACY_BEGIN.match(s):
            in_legacy = True
            continue
        if s == LEGACY_END:
            in_legacy = False
            continue
        if in_legacy:
            continue                                  # legacy block dropped; values carried to paths.conf
        if not s.startswith("#") and KEYWORDS.search(line):
            new = line
            for old, nw in prefix_map:
                new = new.replace(old, nw)
            if new != line:
                out.append(new)
                continue
            stale = [t for t in PATH_TOKEN.findall(line)
                     if (p := expand(t)) is not None and len(str(p)) > 1 and not p.exists()]
            if stale and re.search(r"ONBOARDED_DIR|ob_dispatcher|ob_profile|/onboarded|msi[-_]nav|MSI_NAV_DIR", line):
                out.append(f"# disabled by ob_paths {stamp} (path gone: {stale[0]}): {line}")
                continue
        out.append(line)
    body = "\n".join(out).rstrip("\n") + "\n"
    if add_block or had_block:
        body += "\n" + MANAGED_BLOCK
    return body


def cmd_fix(a) -> int:
    apply = a.apply
    before = scan()
    conf = read_conf()
    legacy = _legacy_values()
    plan: list[str] = []
    bk = Backup(apply)
    stamp = bk.id

    # ── resolve the paths that live outside the repo ──
    new = dict(conf)
    if a.workspace:
        new["OB_WORKSPACE"] = str(Path(a.workspace).expanduser().resolve())
    elif not conf_path(conf, "OB_WORKSPACE") or not conf_path(conf, "OB_WORKSPACE").is_dir():
        # an existing folder with data beats creating a new empty one; the old name keeps
        # working until you run move-workspace
        for cand in (os.environ.get("OB_WORKSPACE"), str(DEFAULT_WORKSPACE), str(LEGACY_WORKSPACE)):
            if cand and Path(cand).expanduser().is_dir() and not workspace_conflict(Path(cand)):
                new["OB_WORKSPACE"] = str(Path(cand).expanduser())
                break
        else:
            new["OB_WORKSPACE"] = str(DEFAULT_WORKSPACE)
    if (why := workspace_conflict(Path(new["OB_WORKSPACE"]))):
        raise SystemExit(f"✖ OB_WORKSPACE: {why}.\n  Pick another folder: --workspace {suggest_workspace()} "
                         f"(or move this checkout, e.g. to ~/develop/onboarded)")
    old_msi = conf_path(conf, "MSI_NAV_DIR") or Path(os.environ.get("MSI_NAV_DIR") or HOME / "msi-nav")
    msi_wanted = bool(conf.get("MSI_NAV_DIR") or os.environ.get("MSI_NAV_DIR") or before.old_msi)
    if getattr(a, "no_msi_nav", False):
        if new.pop("MSI_NAV_DIR", None):
            plan.append("note  MSI_NAV_DIR removed (--no-msi-nav)")
    elif a.msi_nav:
        new["MSI_NAV_DIR"] = str(Path(a.msi_nav).expanduser().resolve())
    elif msi_wanted and not (conf_path(conf, "MSI_NAV_DIR") and conf_path(conf, "MSI_NAV_DIR").is_dir()):
        envmn = os.environ.get("MSI_NAV_DIR")
        cands = ([Path(envmn)] if envmn else []) + msi_nav_candidates()
        found = next((p for p in cands if p.is_dir()), None)
        if found:
            new["MSI_NAV_DIR"] = str(found)
            plan.append(f"note  MSI_NAV_DIR auto-detected: {tilde(found)}")
        else:
            plan.append("note  MSI_NAV_DIR not found under ~ — left unset (optional; --msi-nav PATH to set it)")
            new.pop("MSI_NAV_DIR", None) if new.get("MSI_NAV_DIR") and not Path(new["MSI_NAV_DIR"]).is_dir() else None
    if a.repos_root:
        new["OB_REPOS_ROOT"] = str(Path(a.repos_root).expanduser().resolve())
    elif "OB_REPOS_ROOT" not in new and legacy.get("OB_ROOT"):
        new["OB_REPOS_ROOT"] = legacy["OB_ROOT"]
    if a.default_tenant:
        new["OB_DEFAULT_TENANT"] = a.default_tenant
    elif "OB_DEFAULT_TENANT" not in new and legacy.get("OB_TENANT"):
        new["OB_DEFAULT_TENANT"] = legacy["OB_TENANT"]
    for k in [k for k in CONF_PATH_KEYS if k in new and " " in new[k]]:
        plan.append(f"warn  {k} contains a space; the Makefile cannot read it (move the directory or rename)")

    # 0. the workspace folder itself (instances are created inside it)
    wsp = Path(new["OB_WORKSPACE"])
    if not wsp.is_dir():
        plan.append(f"mkdir {tilde(wsp)}  — instance workspace")
        if apply:
            wsp.mkdir(parents=True, exist_ok=True)

    # 1. stable root link
    _symlink(ROOT_LINK, REPO, bk, apply, plan, "the one stable path ~/.zshrc uses")

    # 2. paths.conf
    lines = ["# ~/.onboarded/paths.conf — paths onboarded needs that live OUTSIDE the repo.",
             "# Read by ob_profile.zsh, the Makefile (include), the justfile and ob_instance.py.",
             "# Plain KEY=value, absolute paths, no quotes. Repair with: obpaths fix --apply",
             f"# Last written {stamp} by {tilde(Path(__file__).resolve())}"]
    lines += [f"{k}={new[k]}" for k in CONF_KEYS if new.get(k)]
    lines += [f"{k}={v}" for k, v in new.items() if k not in CONF_KEYS]
    if new != conf or not CONF.is_file():
        _write(CONF, "\n".join(lines) + "\n", bk, apply, plan, "foundational paths")

    # 3. shell profiles
    prefix_map = []
    if a.from_ and a.to:
        prefix_map.append((str(Path(a.from_).expanduser()).rstrip("/"), str(Path(a.to).expanduser()).rstrip("/")))
    for old in sorted(before.old_roots):
        if old.rstrip("/") != str(REPO):
            prefix_map.append((old.rstrip("/"), str(REPO)))
    if new.get("MSI_NAV_DIR"):
        for om in sorted({str(old_msi)} | before.old_msi):
            if not Path(om).is_dir() and om != new["MSI_NAV_DIR"]:
                prefix_map.append((om, new["MSI_NAV_DIR"]))
    # each mapping also in its ~/ and $HOME spellings, as profiles use all three
    variants = []
    for old, nw in prefix_map:
        plan.append(f"map   {tilde(old)} → {tilde(nw)}  (in shell profiles)")
        variants.append((old, nw))
        if old.startswith(str(HOME) + "/") and nw.startswith(str(HOME) + "/"):
            variants.append(("~" + old[len(str(HOME)):], "~" + nw[len(str(HOME)):]))
            variants.append(("$HOME" + old[len(str(HOME)):], "$HOME" + nw[len(str(HOME)):]))
    prefix_map = variants
    main_rc = primary_rc()
    for f in rc_files():
        if not f.is_file() and f != main_rc:
            continue
        text = f.read_text(errors="replace") if f.is_file() else ""
        has_block = BEGIN in text
        new_text = rewrite_profile(text, prefix_map, stamp, add_block=(f == main_rc and not has_block))
        _write(f, new_text, bk, apply, plan, "managed block / legacy block / stale lines")

    # 4. instance env files + overlays + active + git exclude
    mans = instance_manifests()
    ws = Path(new["OB_WORKSPACE"])
    for kind, base in (("instance", REPO / "instances"), ("tenant", REPO / "packages/core/tenants"),
                       ("templates", REPO / "templates")):
        if base.is_dir():
            for p in sorted(base.iterdir()):
                if p.is_symlink() and not Path(os.readlink(p)).exists():
                    want = ws / p.name / "overlay" / kind
                    if want.exists():
                        _symlink(p, want, bk, apply, plan, "confidential overlay")
                    else:
                        plan.append(f"warn  {p.relative_to(REPO)}: overlay not found at {tilde(want)} — "
                                    f"pass --workspace, or restore the workspace")
    if apply:
        mans = instance_manifests()             # confidential manifests reappear once relinked
    else:
        for base in (REPO / "instances",):
            for p in sorted(base.iterdir()) if base.is_dir() else []:
                if p.is_symlink() and p.name not in mans and (ws / p.name / "overlay" / "instance" / "instance.json").is_file():
                    mans[p.name] = json.loads((ws / p.name / "overlay" / "instance" / "instance.json").read_text())
    for slug in mans:
        ef = OBH / "instances" / f"{slug}.env"
        plan.append(f"regen {tilde(ef)}")
        if apply:
            bk.file(ef)
            env = dict(os.environ, OB_WORKSPACE=str(ws))
            env.pop("ONBOARDED_DIR", None)
            p = subprocess.run([sys.executable, str(REPO / "packages/core/scripts/ob_instance.py"), "env", slug],
                               env=env, capture_output=True, text=True)
            if p.returncode:
                plan.append(f"warn  {slug}.env: {p.stderr.strip()[:160]}")
    act = OBH / "active"
    if act.is_file() and act.read_text().strip() not in mans:
        plan.append(f"clear ~/.onboarded/active ({act.read_text().strip()} is not an instance here)")
        if apply:
            bk.file(act)
            act.unlink()
    if any(m.get("classification") == "confidential" for m in mans.values()):
        plan.append("sync  .git/info/exclude confidential block")
        if apply:
            spec = importlib.util.spec_from_file_location("ob_instance", REPO / "packages/core/scripts/ob_instance.py")
            mod = importlib.util.module_from_spec(spec)
            os.environ["OB_WORKSPACE"] = str(ws)
            spec.loader.exec_module(mod)
            mod.sync_git_exclude()

    bid = bk.close()
    print(c("1", "Plan" if not apply else "Applied"))
    for line in plan or ["nothing to change"]:
        print("  " + line)
    if not apply:
        print(c("33", "\nDry run — nothing written. Re-run with --apply."))
        return 0
    if bid:
        print(c("2", f"\nBackup: {tilde(BACKUPS / bid)}   (undo: ob_paths.py restore {bid} --apply)"))
    after = scan()
    print()
    rc = print_report(after)
    print(c("1", "\nOpen a new shell (or: exec zsh) so the current one drops stale exported values."))
    return rc


def cmd_move_workspace(a) -> int:
    conf = read_conf()
    old = workspace_now(conf)
    newp = Path(a.new).expanduser().resolve()
    if (why := workspace_conflict(newp)):
        raise SystemExit(f"✖ {why}")
    if newp.exists() and newp.is_dir() and not any(newp.iterdir()):
        if a.apply:
            newp.rmdir()                                  # an empty folder is fine to move onto
    elif newp.exists():
        raise SystemExit(f"✖ {tilde(newp)} already exists and is not empty — move its contents aside first")
    if not old.is_dir():
        raise SystemExit(f"✖ current workspace {old} does not exist; use: fix --workspace {newp}")
    print(f"move  {tilde(old)} → {tilde(newp)}")
    if a.apply:
        newp.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(old), str(newp))
    a.workspace, a.msi_nav, a.repos_root, a.default_tenant, a.from_, a.to = str(newp), None, None, None, None, None
    a.no_msi_nav = False
    if not a.apply:
        print(c("33", "Dry run — nothing moved. Re-run with --apply."))
        return 0
    return cmd_fix(a)


def cmd_where(a) -> int:
    conf = read_conf()
    rows = [("ONBOARDED_DIR (this checkout)", REPO),
            ("~/.onboarded/root", Path(os.readlink(ROOT_LINK)) if ROOT_LINK.is_symlink() else "—"),
            ("MSI_NAV_DIR", conf.get("MSI_NAV_DIR", "—")),
            ("OB_WORKSPACE", workspace_now(conf)),
            ("OB_REPOS_ROOT", conf.get("OB_REPOS_ROOT", "—")),
            ("OB_DEFAULT_TENANT", conf.get("OB_DEFAULT_TENANT", "—")),
            ("active instance", (OBH / "active").read_text().strip() if (OBH / "active").is_file() else "—"),
            ("profile", primary_rc())]
    for k, v in rows:
        print(f"  {k:32} {tilde(v)}")
    return 0


def cmd_env(a) -> int:
    conf = read_conf()
    print(f'export ONBOARDED_DIR="{REPO}"')
    for k in CONF_KEYS:
        if conf.get(k):
            print(f'export {k}="{conf[k]}"')
    if conf.get("OB_REPOS_ROOT"):
        print(f'export OB_ROOT="{conf["OB_REPOS_ROOT"]}"')
    return 0


def cmd_backups(a) -> int:
    if not BACKUPS.is_dir() or not any(BACKUPS.iterdir()):
        print("  no backups")
        return 0
    for d in sorted(BACKUPS.iterdir()):
        m = d / "manifest.json"
        if m.is_file():
            meta = json.loads(m.read_text())
            print(f"  {d.name}  {len(meta['files'])} file(s), {len(meta['links'])} link(s)  from {tilde(meta.get('repo', '?'))}")
    return 0


def cmd_restore(a) -> int:
    d = BACKUPS / a.id
    m = d / "manifest.json"
    if not m.is_file():
        raise SystemExit(f"✖ no backup {a.id} (see: ob_paths.py backups)")
    meta = json.loads(m.read_text())
    for orig, name in meta["files"].items():
        print(f"restore {tilde(orig)}")
        if a.apply:
            Path(orig).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(d / "files" / name, orig)
    for orig in meta.get("new_files", []):
        print(f"remove  {tilde(orig)}  (created by that fix)")
        if a.apply and Path(orig).is_file():
            Path(orig).unlink()
    for orig, tgt in meta["links"].items():
        p = Path(orig)
        print(f"relink  {tilde(orig)} → {tilde(tgt) if tgt else '(removed)'}")
        if a.apply:
            if p.is_symlink() or p.is_file():
                p.unlink()
            if tgt:
                p.symlink_to(tgt, target_is_directory=True)
    if not a.apply:
        print(c("33", "Dry run — re-run with --apply."))
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="obpaths", description="Find and repair onboarded's foundational paths.")
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("check")
    sub.add_parser("where")
    sub.add_parser("env")
    sub.add_parser("backups")
    f = sub.add_parser("fix")
    for x in (f,):
        x.add_argument("--apply", action="store_true")
        x.add_argument("--workspace")
        x.add_argument("--msi-nav", dest="msi_nav")
        x.add_argument("--no-msi-nav", dest="no_msi_nav", action="store_true",
                       help="drop MSI_NAV_DIR from paths.conf (msi-nav is optional)")
        x.add_argument("--repos-root", dest="repos_root")
        x.add_argument("--default-tenant", dest="default_tenant")
        x.add_argument("--from", dest="from_")
        x.add_argument("--to")
    mv = sub.add_parser("move-workspace")
    mv.add_argument("new")
    mv.add_argument("--apply", action="store_true")
    rs = sub.add_parser("restore")
    rs.add_argument("id")
    rs.add_argument("--apply", action="store_true")
    a = p.parse_args(argv)
    if a.cmd in (None, "check"):
        return print_report(scan())
    if a.cmd == "fix" and bool(a.from_) != bool(a.to):
        raise SystemExit("✖ --from and --to go together")
    return {"where": cmd_where, "env": cmd_env, "backups": cmd_backups, "fix": cmd_fix,
            "move-workspace": cmd_move_workspace, "restore": cmd_restore}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
