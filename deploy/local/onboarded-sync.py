#!/usr/bin/env python3
"""
onboarded-sync — ship the Onboarded dev repo to its running location.

    ~/develop/integrations/onboarded   (dev: git, docs, tests, node_modules…)
                 │  release.manifest (allowlist)
                 ▼
    ~/onboarded                        (running copy: only the runtime payload)

Commands
    onboarded-sync                 show the plan, confirm, apply   (default)
    onboarded-sync plan            show what would change, touch nothing
    onboarded-sync status          what's deployed vs what's in dev
    onboarded-sync files           list every file the manifest ships
    onboarded-sync rollback        restore the running copy from the last backup

Safety
    • Only files listed in the manifest are ever written.
    • Only files a previous sync wrote are ever deleted — anything else in the
      running copy (local config, notes, a .env) is left alone.
    • Files edited by hand in the running copy since the last sync are
      detected; the sync stops unless you pass --force.
    • Every apply backs up the files it will overwrite or delete first.
    • Runtime data in ~/.onboarded/<tenant>/ (telemetry, tickets) is never
      touched — it lives outside the running copy.

Requires Python 3.9+ (already required by Onboarded). Uses git if present.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

VERSION = "1.0.0"
HERE = Path(__file__).resolve().parent            # …/deploy/local
DEFAULT_SRC = HERE.parent.parent                  # repo root
STATE_FILE = ".onboarded-release.json"            # lives in DEST

DEFAULTS = {
    "DEST": "~/onboarded",
    "TENANTS": "msi",
    "SMOKE_TENANT": "msi",
    "VALIDATE": "1",
    "SMOKE": "1",
    "KEEP_BACKUPS": "5",
    "BACKUP_DIR": "~/.local/state/onboarded-sync/backups",
}


# ── output ────────────────────────────────────────────────────────────────── #
_TTY = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


def _c(code: str, s: str) -> str:
    return f"\033[{code}m{s}\033[0m" if _TTY else s


def bold(s): return _c("1", s)
def dim(s): return _c("2", s)
def red(s): return _c("31", s)
def green(s): return _c("32", s)
def yellow(s): return _c("33", s)
def cyan(s): return _c("36", s)


def info(msg=""): print(msg)
def warn(msg): print(f"{yellow('!')} {msg}")


class SyncError(Exception):
    pass


def tilde(p: Path) -> str:
    home = str(Path.home())
    s = str(p)
    return "~" + s[len(home):] if s == home or s.startswith(home + os.sep) else s


# ── config ────────────────────────────────────────────────────────────────── #
def load_conf(path: Path) -> dict:
    conf = dict(DEFAULTS)
    if path.is_file():
        for n, raw in enumerate(path.read_text().splitlines(), 1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                raise SyncError(f"{path}:{n}: expected KEY=VALUE, got: {raw}")
            k, v = line.split("=", 1)
            conf[k.strip()] = v.strip().strip('"').strip("'")
    for k in list(conf):
        env = os.environ.get(f"ONBOARDED_SYNC_{k}")
        if env is not None:
            conf[k] = env
    return conf


def expand(p: str) -> Path:
    return Path(os.path.expandvars(os.path.expanduser(p))).resolve()


# ── manifest ──────────────────────────────────────────────────────────────── #
def glob_to_regex(pattern: str) -> re.Pattern:
    i, out = 0, []
    while i < len(pattern):
        ch = pattern[i]
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?"); i += 3
        elif pattern.startswith("**", i):
            out.append(".*"); i += 2
        elif ch == "*":
            out.append("[^/]*"); i += 1
        elif ch == "?":
            out.append("[^/]"); i += 1
        else:
            out.append(re.escape(ch)); i += 1
    return re.compile("^" + "".join(out) + "$")


def load_manifest(path: Path, tenants: list[str]):
    if not path.is_file():
        raise SyncError(f"manifest not found: {path}")
    inc, exc = [], []
    for n, raw in enumerate(path.read_text().splitlines(), 1):
        line = raw.split(" #", 1)[0].strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 1)
        if len(parts) != 2 or parts[0] not in ("include", "exclude"):
            raise SyncError(f"{path.name}:{n}: expected 'include <glob>' or 'exclude <glob>'")
        kind, pat = parts
        pats = [pat.replace("{tenant}", t) for t in tenants] if "{tenant}" in pat else [pat]
        (inc if kind == "include" else exc).extend(glob_to_regex(p.strip("/")) for p in pats)
    if not inc:
        raise SyncError(f"{path.name} has no include lines — nothing would ship")
    return inc, exc


PRUNE_DIRS = {".git", "node_modules", ".nx", ".angular", "__pycache__", ".pytest_cache", ".venv", "venv"}


def select_files(src: Path, inc, exc) -> list[str]:
    chosen = []
    for root, dirs, files in os.walk(src):
        dirs[:] = sorted(d for d in dirs if d not in PRUNE_DIRS)
        rel_root = os.path.relpath(root, src).replace(os.sep, "/")
        for f in sorted(files):
            rel = f if rel_root == "." else f"{rel_root}/{f}"
            if any(r.match(rel) for r in inc) and not any(r.match(rel) for r in exc):
                if os.path.isfile(os.path.join(root, f)):  # skip broken symlinks
                    chosen.append(rel)
    return chosen


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


# ── git ───────────────────────────────────────────────────────────────────── #
def git(src: Path, *args, check=True) -> str:
    try:
        r = subprocess.run(["git", "-C", str(src), *args], capture_output=True, text=True)
    except FileNotFoundError:
        if check:
            raise SyncError("git is not installed")
        return ""
    if r.returncode != 0:
        if check:
            raise SyncError(f"git {' '.join(args)}: {r.stderr.strip()}")
        return ""
    return r.stdout.strip()


def git_info(src: Path, shipped: list[str] | None = None) -> dict:
    if not (src / ".git").exists():
        return {}
    info_ = {
        "commit": git(src, "rev-parse", "HEAD", check=False),
        "branch": git(src, "branch", "--show-current", check=False) or "detached",
        "describe": git(src, "describe", "--tags", "--always", "--dirty", check=False),
    }
    porcelain = git(src, "status", "--porcelain", check=False).splitlines()
    changed = {line[3:].split(" -> ")[-1].strip('"') for line in porcelain}
    info_["dirty_files"] = sorted(changed & set(shipped)) if shipped is not None else sorted(changed) # pyright: ignore[reportArgumentType]
    return info_


def export_ref(src: Path, ref: str, into: Path) -> dict:
    commit = git(src, "rev-parse", "--verify", f"{ref}^{{commit}}")
    archive = into / "src.tar"
    with open(archive, "wb") as fh:
        r = subprocess.run(["git", "-C", str(src), "archive", "--format=tar", commit], stdout=fh)
    if r.returncode != 0:
        raise SyncError(f"git archive {ref} failed")
    tree = into / "tree"
    tree.mkdir()
    with tarfile.open(archive) as tf:
        _safe_extract(tf, tree)
    return {"commit": commit, "branch": ref, "describe": git(src, "describe", "--tags", "--always", commit, check=False),
            "dirty_files": []}


def _safe_extract(tf: tarfile.TarFile, dest: Path):
    dest = dest.resolve()
    for m in tf.getmembers():
        target = (dest / m.name).resolve()
        if dest != target and dest not in target.parents:
            raise SyncError(f"refusing unsafe path in archive: {m.name}")
    _extract(tf, dest)


def _extract(tf: tarfile.TarFile, dest: Path, members=None):
    # Python 3.12+ warns unless an extraction filter is given; older versions lack it.
    if hasattr(tarfile, "data_filter"):
        tf.extractall(dest, members=members, filter="data")
    else:
        tf.extractall(dest, members=members)


# ── state ─────────────────────────────────────────────────────────────────── #
def read_state(dest: Path) -> dict:
    p = dest / STATE_FILE
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text())
    except json.JSONDecodeError:
        raise SyncError(f"{p} is corrupt — move it aside to start fresh")


def write_state(dest: Path, state: dict):
    tmp = dest / (STATE_FILE + ".tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
    os.replace(tmp, dest / STATE_FILE)


# ── planning ──────────────────────────────────────────────────────────────── #
def plan(src: Path, dest: Path, files: list[str], state: dict) -> dict:
    prev = state.get("files", {})
    new_hashes = {rel: sha256(src / rel) for rel in files}
    add, update, same, drifted = [], [], [], []
    for rel, h in new_hashes.items():
        target = dest / rel
        if not target.exists():
            add.append(rel)
            continue
        cur = sha256(target) if target.is_file() else None
        if rel in prev and cur != prev[rel]:
            drifted.append(rel)           # hand-edited in DEST since last sync
        if cur == h:
            same.append(rel)
        else:
            update.append(rel)
    remove = sorted(r for r in prev if r not in new_hashes and (dest / r).exists())
    for rel in remove:
        if sha256(dest / rel) != prev[rel]:
            drifted.append(rel)
    # files that exist in DEST, were never ours, and would now be overwritten
    foreign = [r for r in update if r not in prev]
    return {"hashes": new_hashes, "add": add, "update": update, "remove": remove,
            "same": same, "drifted": sorted(set(drifted)), "foreign": foreign}


def print_plan(p: dict, verbose: bool):
    n_add, n_upd, n_rm = len(p["add"]), len(p["update"]), len(p["remove"])
    if not (n_add or n_upd or n_rm):
        info(green("✓ running copy is already up to date") + dim(f"  ({len(p['same'])} files)"))
        return
    n_same = len(p["same"])
    info(f"  {green(f'+{n_add} new')}   {yellow(f'~{n_upd} changed')}   {red(f'-{n_rm} removed')}"
         f"   {dim(f'{n_same} unchanged')}")
    limit = None if verbose else 25
    rows = [(green("+"), r) for r in p["add"]] + [(yellow("~"), r) for r in p["update"]] + \
           [(red("-"), r) for r in p["remove"]]
    rows.sort(key=lambda x: x[1])
    for mark, rel in rows[:limit]:
        flag = red("  (edited in running copy)") if rel in p["drifted"] else ""
        info(f"    {mark} {rel}{flag}")
    if limit and len(rows) > limit:
        info(dim(f"    … {len(rows) - limit} more (use -v to list all)"))


# ── backup / apply / rollback ─────────────────────────────────────────────── #
def backup(dest: Path, rels: list[str], backup_dir: Path, label: str, keep: int) -> Path | None:
    existing = [r for r in rels if (dest / r).is_file()]
    if not existing and not (dest / STATE_FILE).exists():
        return None
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    path = backup_dir / f"{stamp}-{label}.tar.gz"
    with tarfile.open(path, "w:gz") as tf:
        for r in existing:
            tf.add(dest / r, arcname=r)
        if (dest / STATE_FILE).exists():
            tf.add(dest / STATE_FILE, arcname=STATE_FILE)
        # record which paths the backup covers, including ones that did not exist
        meta = json.dumps({"dest": str(dest), "paths": rels}).encode()
        ti = tarfile.TarInfo(".backup-meta.json"); ti.size = len(meta)
        tf.addfile(ti, io.BytesIO(meta))
    backups = sorted(backup_dir.glob("*.tar.gz"))
    for old in backups[:-keep] if keep > 0 else []:
        old.unlink()
    return path


def apply(src: Path, dest: Path, p: dict):
    for rel in p["add"] + p["update"]:
        s, t = src / rel, dest / rel
        t.parent.mkdir(parents=True, exist_ok=True)
        tmp = t.with_name(f".{t.name}.onboarded-sync.tmp")
        shutil.copy2(s, tmp)
        os.replace(tmp, t)
    for rel in p["remove"]:
        (dest / rel).unlink(missing_ok=True)
        _prune_empty(dest, (dest / rel).parent)


def _prune_empty(dest: Path, d: Path):
    while d != dest and dest in d.parents:
        try:
            d.rmdir()
        except OSError:
            return
        d = d.parent


def rollback(dest: Path, backup_dir: Path, assume_yes: bool) -> int:
    backups = sorted(backup_dir.glob("*.tar.gz")) if backup_dir.is_dir() else []
    if not backups:
        raise SyncError(f"no backups in {tilde(backup_dir)}")
    latest = backups[-1]
    with tarfile.open(latest) as tf:
        meta = json.loads(tf.extractfile(".backup-meta.json").read()) # pyright: ignore[reportOptionalMemberAccess]
        names = set(tf.getnames())
    if Path(meta["dest"]) != dest:
        raise SyncError(f"latest backup is for {meta['dest']}, not {dest}")
    info(f"Restore {bold(tilde(dest))} from {cyan(latest.name)}")
    info(dim(f"  {len(meta['paths'])} paths covered; files added by that sync are removed"))
    if not confirm(assume_yes):
        return 1
    for rel in meta["paths"]:
        if rel not in names:                     # didn't exist before that sync
            (dest / rel).unlink(missing_ok=True)
            _prune_empty(dest, (dest / rel).parent)
    if STATE_FILE not in names:
        (dest / STATE_FILE).unlink(missing_ok=True)
    with tarfile.open(latest) as tf:
        members = [m for m in tf.getmembers() if m.name != ".backup-meta.json"]
        for m in members:
            target = (dest / m.name).resolve()
            if dest not in target.parents and target != dest:
                raise SyncError(f"refusing unsafe path in backup: {m.name}")
        _extract(tf, dest, members)
    latest.unlink()
    info(green("✓ rolled back") + dim(f"  ({len(backups) - 1} older backup(s) remain)"))
    return 0


# ── checks ────────────────────────────────────────────────────────────────── #
def validate(src: Path, tenants: list[str]) -> bool:
    script = src / "packages/core/scripts/validate_domain.py"
    if not script.is_file():
        warn("validate_domain.py not found — skipping validation")
        return True
    ok = True
    for t in tenants:
        r = subprocess.run([sys.executable, str(script), "--tenant", t], cwd=src,
                           capture_output=True, text=True)
        if r.returncode == 0:
            info(f"  {green('✓')} domain valid: {t}")
        else:
            ok = False
            info(f"  {red('✗')} domain invalid: {t}")
            for line in (r.stdout + r.stderr).strip().splitlines()[-15:]:
                info(dim(f"      {line}"))
    return ok


def smoke(dest: Path, tenant: str) -> bool:
    zsh = shutil.which("zsh")
    if not zsh:
        warn("zsh not found — skipping smoke test")
        return True
    dispatcher = dest / "packages/cli/src/ob_dispatcher.zsh"
    if not dispatcher.is_file():
        info(f"  {red('✗')} smoke: {tilde(dispatcher)} missing")
        return False
    env = {k: v for k, v in os.environ.items() if k not in ("ONBOARDED_DIR",) and not k.startswith("_OB_")}
    env["OB_TENANT"] = tenant
    script = (f'source {json.dumps(str(dispatcher))} >/dev/null || exit 3; '
              '(( $+functions[_ob_help] )) || exit 4; print -r -- "${OB_CLI_NAME}"')
    r = subprocess.run([zsh, "-fc", script], capture_output=True, text=True, env=env, timeout=60)
    if r.returncode == 0:
        info(f"  {green('✓')} smoke: running copy loads on its own (cli: {r.stdout.strip() or '?'})")
        return True
    info(f"  {red('✗')} smoke: dispatcher failed to load from {tilde(dest)} (exit {r.returncode})")
    for line in r.stderr.strip().splitlines()[-10:]:
        info(dim(f"      {line}"))
    return False


def confirm(assume_yes: bool) -> bool:
    if assume_yes:
        return True
    if not sys.stdin.isatty():
        raise SyncError("not a terminal — pass -y to apply without confirmation")
    return input(f"{bold('Apply?')} [y/N] ").strip().lower() in ("y", "yes")


# ── commands ──────────────────────────────────────────────────────────────── #
def resolve(args, conf):
    src = expand(args.src) if args.src else Path(os.environ.get("ONBOARDED_SYNC_SRC", DEFAULT_SRC)).resolve()
    dest = expand(args.dest or conf["DEST"])
    tenants = (args.tenants or conf["TENANTS"]).replace(",", " ").split()
    if not tenants:
        raise SyncError("no tenants configured")
    if dest == src or src in dest.parents or dest in src.parents:
        raise SyncError(f"source {src} and destination {dest} overlap")
    if dest in (Path.home(), Path("/")):
        raise SyncError(f"refusing to use {dest} as the destination")
    return src, dest, tenants


def cmd_sync(args, conf, dry: bool) -> int:
    src, dest, tenants = resolve(args, conf)
    manifest = expand(args.manifest) if args.manifest else HERE / "release.manifest"
    inc, exc = load_manifest(manifest, tenants)

    with tempfile.TemporaryDirectory(prefix="onboarded-sync-") as tmp:
        if args.ref:
            meta = export_ref(src, args.ref, Path(tmp))
            payload_root = Path(tmp) / "tree"
            origin = f"git {args.ref}"
        else:
            payload_root = src
            origin = "working tree"

        files = select_files(payload_root, inc, exc)
        if not files:
            raise SyncError("the manifest matched no files — check release.manifest and TENANTS")
        if not args.ref:
            meta = git_info(src, files)

        info(f"{bold('onboarded-sync')} {dim('v' + VERSION)}")
        info(f"  from  {tilde(src)}  {dim('(' + origin + ')')}")
        info(f"  to    {tilde(dest)}")
        if meta: # pyright: ignore[reportPossiblyUnboundVariable]
            info(f"  rev   {meta.get('describe') or meta['commit'][:10]} {dim('on ' + meta['branch'])}")
            if meta["dirty_files"]:
                warn(f"{len(meta['dirty_files'])} shipped file(s) have uncommitted changes "
                     f"{dim('(recorded in the release stamp)')}")
        info(f"  ship  {len(files)} files · tenants: {', '.join(tenants)}")
        info()

        if conf["VALIDATE"] == "1" and not args.no_validate:
            if not validate(payload_root, tenants):
                raise SyncError("domain validation failed — fix it or pass --no-validate")
            info()

        state = read_state(dest) if dest.exists() else {}
        p = plan(payload_root, dest, files, state)
        print_plan(p, args.verbose)

        if p["drifted"] and not args.force:
            info()
            warn(f"{len(p['drifted'])} file(s) were edited directly in {tilde(dest)} since the last sync:")
            for r in p["drifted"][:10]:
                info(f"    {r}")
            raise SyncError("copy those edits back to dev first, or pass --force to overwrite them")
        if p["foreign"] and not state and not args.force:
            info()
            warn(f"{tilde(dest)} already has {len(p['foreign'])} file(s) this sync would overwrite, "
                 "and no previous sync recorded them")
            raise SyncError("pass --force to take over the existing files (a backup is made first)")

        changes = p["add"] or p["update"] or p["remove"]
        if dry:
            if changes:
                info(dim("\n  plan only — nothing changed. Run `onboarded-sync` to apply."))
            return 0
        if not changes and state.get("commit") == (meta or {}).get("commit"): # pyright: ignore[reportPossiblyUnboundVariable]
            return 0

        if changes:
            info()
            if not confirm(args.yes):
                info("aborted")
                return 1
            dest.mkdir(parents=True, exist_ok=True)
            label = (meta.get("commit", "")[:7] if meta else "") or "sync" # pyright: ignore[reportPossiblyUnboundVariable]
            bpath = backup(dest, p["update"] + p["remove"] + p["add"], expand(conf["BACKUP_DIR"]),
                           label, int(conf["KEEP_BACKUPS"]))
            apply(payload_root, dest, p)

        write_state(dest, {
            "tool": f"onboarded-sync {VERSION}",
            "synced_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
            "source": str(src),
            "origin": origin,
            "commit": (meta or {}).get("commit"), # pyright: ignore[reportPossiblyUnboundVariable]
            "branch": (meta or {}).get("branch"), # pyright: ignore[reportPossiblyUnboundVariable]
            "describe": (meta or {}).get("describe"), # pyright: ignore[reportPossiblyUnboundVariable]
            "dirty_files": (meta or {}).get("dirty_files", []), # pyright: ignore[reportPossiblyUnboundVariable]
            "tenants": tenants,
            "files": p["hashes"],
        })
        if changes:
            info(green(f"\n✓ synced {len(p['add']) + len(p['update'])} file(s), removed {len(p['remove'])}")
                 + (dim(f"  · backup: {tilde(bpath)}") if bpath else "")) # pyright: ignore[reportPossiblyUnboundVariable]

    if conf["SMOKE"] == "1" and not args.no_smoke:
        if not smoke(dest, conf.get("SMOKE_TENANT") or tenants[0]):
            info(dim("  undo with: onboarded-sync rollback"))
            return 2
    return 0


def cmd_status(args, conf) -> int:
    src, dest, tenants = resolve(args, conf)
    state = read_state(dest) if dest.exists() else {}
    info(bold("Running copy") + f"  {tilde(dest)}")
    if not state:
        info(dim("  never synced" + ("" if dest.exists() else " (directory does not exist)")))
    else:
        rev = state.get("describe") or (state.get("commit") or "")[:10] or "?"
        info(f"  release  {rev} {dim('on ' + str(state.get('branch')))} · {state['synced_at']} · {state['origin']}")
        if state.get("dirty_files"):
            warn(f"  shipped with {len(state['dirty_files'])} uncommitted file(s)")
        edited = [r for r, h in state["files"].items() if (dest / r).is_file() and sha256(dest / r) != h]
        missing = [r for r in state["files"] if not (dest / r).exists()]
        line = f"  files    {len(state['files'])} managed"
        line += f" · {red(str(len(edited)) + ' edited in place')}" if edited else f" · {green('0 edited in place')}"
        if missing:
            line += f" · {red(str(len(missing)) + ' missing')}"
        info(line)
        for r in (edited + missing)[:10]:
            info(dim(f"      {r}"))
    info()
    info(bold("Dev repo") + f"      {tilde(src)}")
    gi = git_info(src)
    if gi:
        info(f"  HEAD     {gi['describe']} {dim('on ' + gi['branch'])}")
        if state.get("commit") and state["commit"] != gi["commit"]:
            ahead = git(src, "rev-list", "--count", f"{state['commit']}..HEAD", check=False)
            if ahead:
                info(f"  ahead    {ahead} commit(s) since the deployed release")
    inc, exc = load_manifest(expand(args.manifest) if args.manifest else HERE / "release.manifest", tenants)
    files = select_files(src, inc, exc)
    p = plan(src, dest, files, state)
    n = len(p["add"]) + len(p["update"]) + len(p["remove"])
    if n:
        info(f"  pending  {green('+' + str(len(p['add'])))} {yellow('~' + str(len(p['update'])))} "
             f"{red('-' + str(len(p['remove'])))}  {dim('→ onboarded-sync plan')}")
    else:
        info(f"  pending  {green('nothing — in sync')}")
    return 0


def cmd_files(args, conf) -> int:
    src, _, tenants = resolve(args, conf)
    inc, exc = load_manifest(expand(args.manifest) if args.manifest else HERE / "release.manifest", tenants)
    for rel in select_files(src, inc, exc):
        print(rel)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="onboarded-sync",
        description="Ship the Onboarded dev repo to its running location using release.manifest.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="examples:\n"
               "  onboarded-sync plan            preview\n"
               "  onboarded-sync                 preview, confirm, apply\n"
               "  onboarded-sync --ref v1.1      ship a tagged commit instead of the working tree\n"
               "  onboarded-sync status          deployed vs dev\n"
               "  onboarded-sync rollback        undo the last apply",
    )
    ap.add_argument("command", nargs="?", default="sync",
                    choices=["sync", "apply", "plan", "status", "files", "rollback"])
    ap.add_argument("--ref", help="ship this committed git revision (branch, tag, sha) instead of the working tree")
    ap.add_argument("--dest", help="running copy location (default from sync.conf: ~/onboarded)")
    ap.add_argument("--src", help="dev repo (default: the repo this script lives in)")
    ap.add_argument("--tenants", help="space/comma separated tenants to ship (default from sync.conf)")
    ap.add_argument("--manifest", help="alternate manifest file")
    ap.add_argument("--config", help="alternate sync.conf")
    ap.add_argument("-y", "--yes", action="store_true", help="apply without asking")
    ap.add_argument("--force", action="store_true",
                    help="overwrite files edited in the running copy / take over an unmanaged directory")
    ap.add_argument("--no-validate", action="store_true", help="skip validate_domain.py")
    ap.add_argument("--no-smoke", action="store_true", help="skip the post-sync load test")
    ap.add_argument("-v", "--verbose", action="store_true", help="list every change")
    ap.add_argument("-V", "--version", action="version", version=f"%(prog)s {VERSION}")
    args = ap.parse_args(argv)

    try:
        conf = load_conf(expand(args.config) if args.config else HERE / "sync.conf")
        if args.command in ("sync", "apply"):
            return cmd_sync(args, conf, dry=False)
        if args.command == "plan":
            return cmd_sync(args, conf, dry=True)
        if args.command == "status":
            return cmd_status(args, conf)
        if args.command == "files":
            return cmd_files(args, conf)
        if args.command == "rollback":
            _, dest, _ = resolve(args, conf)
            return rollback(dest, expand(conf["BACKUP_DIR"]), args.yes)
    except SyncError as e:
        print(f"{red('onboarded-sync:')} {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
