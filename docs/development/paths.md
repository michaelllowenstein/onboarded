# Paths — keeping onboarded pointed at the right places

Nothing in the repo hard-codes where the repo lives. Everything that lives
**outside** the repo is written in one file, and your shell profile depends on
one stable link. When anything moves, run one command from the new checkout.

## The three anchors

| Anchor | What it holds | Who reads it |
|---|---|---|
| the checkout itself | `ONBOARDED_DIR`, derived from each script's own location | loader, dispatcher, Makefile, justfile, `ob_instance.py`, `ob-dba`, battery |
| `~/.onboarded/root` | symlink to the checkout | the one managed block in `~/.zshrc` |
| `~/.onboarded/paths.conf` | `MSI_NAV_DIR`, `OB_WORKSPACE`, `OB_REPOS_ROOT`, `OB_DEFAULT_TENANT` | `ob_profile.zsh`, Makefile (`-include`), justfile, `ob_instance.py` |

`~/.zshrc` contains only:

```zsh
# >>> onboarded >>>
[[ -r "$HOME/.onboarded/root/packages/cli/src/ob_profile.zsh" ]] && \
    source "$HOME/.onboarded/root/packages/cli/src/ob_profile.zsh"
# <<< onboarded <<<
```

A stale exported `ONBOARDED_DIR` is ignored (with a warning) rather than
followed, so an old export can no longer break loading.

## When something moves

```bash
cd <wherever the repo is now>
./reorient.sh                                   # check: every stale path, file:line (read-only)
./reorient.sh --apply                           # repair; backs up every file it touches
./reorient.sh --workspace ~/new/ws --msi-nav ~/code/msi-nav --apply   # tell it where things went
./reorient.sh move-workspace ~/new/ws --apply   # move the workspace folder AND repair
./reorient.sh backups                           # list backups
./reorient.sh restore <id> --apply              # undo a repair
exec zsh                                        # drop values the old shell still has exported
```

Same commands: `obpaths …` in zsh, `just paths …`, `make paths ARGS="…"`.

## What `--apply` repairs

| Item | Repair |
|---|---|
| `~/.onboarded/root` | repointed at this checkout |
| `~/.onboarded/paths.conf` | written; msi-nav auto-detected under `~` (depth ≤ 4) if moved |
| shell profiles | legacy bootstrap block removed (its `OB_ROOT` / `OB_TENANT` carried into paths.conf); managed block added once; old repo and msi-nav prefixes rewritten (absolute, `~/` and `$HOME` spellings); onboarded lines whose path is gone are commented out with a dated note |
| instance env files | regenerated for every instance in this checkout |
| confidential overlays | repo symlinks relinked into the current workspace |
| `~/.onboarded/active` | cleared if that instance isn't in this checkout |
| `.git/info/exclude` | confidential block re-synced |

Reported, not changed: Makefile / justfile / bootstrap.sh self-location, and
`deploy/local/sync.conf` DEST (the client install target, which is yours to set).

Paths with spaces: the Makefile cannot read them from paths.conf; the tool warns.
