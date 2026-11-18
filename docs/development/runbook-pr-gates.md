# Runbook — ShellCheck and the PR gate scripts

Operational guide for taking a PR from "branch created" to "merged" with
`scripts/pr.sh`, and for keeping every shell script lint-clean with ShellCheck along
the way. The *why* lives in `docs/roadmap/PR_WORKFLOW.md`; this file is the *how*,
including what to do when something fails.

| You want to… | Go to |
|---|---|
| set up a machine | §1 |
| work a PR start to finish | §2 |
| know what each PR needs before its gate can go green | §3 |
| understand / fix a ShellCheck finding | §4 |
| fix a red, skipped or stale gate | §5 |
| look up a command | §6 |

---

## 1. One-time setup

### 1.1 Check what you have

```bash
cd ~/develop/product/onboarded
scripts/pr.sh doctor
```

`doctor` prints one row per tool with ✔ / ✖ and the gates that need it. Anything ✖
makes those steps **SKIP** in a normal gate and **FAIL** under `--strict`, and `finish`
requires a strict pass, so aim for all ✔ (zsh and gh are optional).

### 1.2 Install the tools

| Tool | Why | Debian/Ubuntu/WSL | macOS (Homebrew) | Windows (native) |
|---|---|---|---|---|
| **bash ≥ 4** | `scripts/pr.sh` uses associative arrays | preinstalled | `brew install bash` (system bash is 3.2) | use WSL |
| **ShellCheck ≥ 0.9** | gates 00, 15 | `sudo apt install shellcheck` | `brew install shellcheck` | `winget install koalaman.shellcheck` / `scoop install shellcheck` |
| zsh | `zsh -n` on CLI scripts (gate 15) | `sudo apt install zsh` | preinstalled | WSL |
| Python ≥ 3.11 + venv | every Python gate | `sudo apt install python3-venv` | `brew install python` | python.org |
| Node 22 + npm | portal builds, `tsc` (09, 12, 13) | nodesource / nvm | `brew install node@22` | nodejs.org |
| Docker + daemon | gate 14, local Postgres | Docker Engine | Docker Desktop / colima | Docker Desktop (WSL2 backend) |
| just | recipes (gate 14 checks them) | `sudo apt install just` (24.04+) or `cargo install just` | `brew install just` | `winget install Casey.Just` |
| gh | `finish --push` opens the PR | `sudo apt install gh` | `brew install gh` | `winget install GitHub.cli` |

If the distro's ShellCheck is older than 0.9, `pip install --user shellcheck-py` ships a
current binary; Docker works too:
`docker run --rm -v "$PWD:/mnt" -w /mnt koalaman/shellcheck:stable -x scripts/pr.sh`.

### 1.3 Project dependencies and database

```bash
just mvp-install                                    # .venv (dba, api[test], admin-cli, feedback) + npm install
just db-init                                        # Postgres :55432, roles, ob_generic + demo data
python3 packages/core/scripts/ob_instance.py pgpass # ~/.pgpass for ob_dba / ob_reader
```

Put these in your shell profile (`~/.zshrc`), because the gates and the DBA engine read them:

```bash
export OB_DB_PORT=55432
export OB_DB_USER=ob_dba
```

`gh auth login` once if you want `finish --push` to open PRs for you.

### 1.4 Editor

Install the ShellCheck extension (VS Code: *ShellCheck* by Timon Wong; JetBrains:
*Shell Script* plugin, which bundles it). Both read the repo's `.shellcheckrc`, so the
editor and `scripts/lint-shell.sh` report the same thing. The extension does not
understand zsh; leave `.zsh` files to `zsh -n` (§4.5).

### 1.5 Line endings (Windows / WSL)

`.gitattributes` forces LF for `*.sh`, `*.zsh`, `*.bats`, `justfile`, `Makefile`. If a
checkout predates it, or you see `$'\r': command not found`:

```bash
git add --renormalize . && git commit -m "chore: normalize line endings"
```

Gate 15 fails on any CRLF shell file, so this cannot slip into a PR unnoticed.

---

## 2. Working a PR, step by step

Example PR **11**; substitute any number. `just pr …` / `just gate …` / `make gate PR=…`
are equivalent shortcuts.

### Step 0 · Before you start

```bash
git status                       # must be clean: start refuses otherwise
scripts/pr.sh list               # where you are: green / stale / - per PR
scripts/pr.sh flow 11            # the routine + smoke list for this PR
```

### Step 1 · Start the branch

```bash
scripts/pr.sh start 11 --patch ~/Downloads/pr-11/PR-11.patch   # from an archive
scripts/pr.sh start 11                                         # or an empty branch to build on
```

`start` checks three things: the tree is clean, the **previous** PR's gate is green *on
this exact commit*, then it creates (or switches to) `feat/admin-cli` and optionally
`git am --3way`s the patch. If it refuses, §5.4.

### Step 2 · Inner loop (repeat while you work)

```bash
scripts/pr.sh gate 11 --fast --only    # this PR only, no slow steps: seconds
scripts/lint-shell.sh --changed        # any shell file you touched (§4)
```

* `--only` skips the regression of earlier gates; drop it once your change settles.
* `-v` prints each passing step's output too.
* A failing step prints the tail of its log; the full log is in `.gates/logs/`.

Commit as you go. Gates run against the working tree; markers are tied to commits.

### Step 3 · Full gate

```bash
scripts/pr.sh gate 11 --strict
```

This re-runs every earlier gate (fast mode) as regression, then all of PR-11
including slow and live steps, and a **missing tool fails** instead of skipping. Green
writes `.gates/11.pass` (HEAD plus a tree fingerprint). It must be run on a clean,
committed tree, or the marker is immediately `stale`.

### Step 4 · Manual smoke

```bash
scripts/pr.sh smoke 11
```

Do each item. `finish` copies the list into the PR body as checkboxes, so tick them there.

### Step 5 · Finish

```bash
scripts/pr.sh finish 11            # dry run: prints the push + gh commands
scripts/pr.sh finish 11 --push     # pushes, opens the PR against feat/api-dba
```

`finish` refuses unless `.gates/11.pass` matches HEAD and the tree is clean.

### Step 6 · After review and merge

```bash
git switch feat/admin-cli && git pull           # the merged branch
scripts/pr.sh gate 11 --strict                  # a merge is a new commit: re-green it
scripts/pr.sh start 12 --patch …/PR-12.patch    # now the next PR may start
```

---

## 3. Per-PR prerequisites

What must be true on your machine for each PR's `--strict` gate to go green, and the
smoke items that need extra setup.

| PR | Branch | Needs (beyond §1) | Notes |
|---|---|---|---|
| 00 | `docs/mvp-roadmap` | shellcheck | first PR: apply with `git am` by hand, `pr.sh` arrives with it |
| 09 | `feat/api-core` | venv with `fastapi uvicorn httpx`, `tsc` (npm install) | live API started by the gate on a random port |
| 10 | `feat/api-dba` | `just db-init`, `OB_DB_PORT/OB_DB_USER`, `~/.pgpass`, `psycopg` | DB steps use `generic:1001`; sandbox clones need no other open sessions on `ob_generic` |
| 11 | `feat/admin-cli` | (as 09) | parity steps compare `--local` vs `--api` JSON |
| 12 | `fix/portal-build` | `npm install` | three production builds: the slowest gate |
| 13 | `feat/portal-api` | `npm install`, venv | smoke needs `just api` + `just portal` in two terminals |
| 14 | `feat/mvp-devstack` | Docker daemon, `just`, `make` | compose e2e builds both images (several minutes first time) |
| 15 | `chore/shell-lint` | shellcheck, zsh | `--changed` lints every shell file this branch touched vs master |
| 16 | `chore/python-entrypoints` | venv | `python -m <pkg> --help` for every package; console scripts resolve |
| 17 | `fix/lint-findings` | shellcheck, zsh, ruff (in `.venv` via `just mvp-install`) | from here `lint-shell.sh --all` is a gate, not just hygiene |

---

## 4. ShellCheck in this repo

### 4.1 What is linted, and how

| Files | Checked by | When |
|---|---|---|
| `scripts/pr.sh`, `scripts/lint-shell.sh`, `scripts/gates/*.sh` | ShellCheck, severity ≥ warning | gates 00 and 15; `lint-shell.sh` with no args |
| any `*.sh` / bash / sh shebang you changed on the branch | ShellCheck | gate 15 (`--changed`); run it yourself in the inner loop |
| every tracked bash/sh script | ShellCheck | `lint-shell.sh --all` (gate 17 onward) |
| `*.zsh` and zsh-shebang files | `zsh -n` (syntax only) | gate 15; ShellCheck does not support zsh |
| `*.bats` | not linted automatically | they source zsh helpers; lint by hand if wanted |

The shebang decides the kind (so `packages/core/scripts/bootstrap.sh`, which starts with
`#!/usr/bin/env zsh`, gets `zsh -n`, not ShellCheck); the extension decides only when
there is no shebang.

### 4.2 Configuration (`.shellcheckrc`)

```ini
external-sources=true     # follow `source` into other files (pr.sh → gates/lib.sh)
source-path=SCRIPTDIR     # resolve `# shellcheck source=` relative to the script
```

Severity is not in the rc file; it's a command-line choice. `lint-shell.sh` uses
`-S warning` (override with `LINT_SEVERITY=style|info|warning|error`).

### 4.3 Commands

```bash
scripts/lint-shell.sh                           # PR tooling (what gate 00 runs)
scripts/lint-shell.sh --changed                 # everything you touched vs master
scripts/lint-shell.sh --changed origin/main     # …vs another base
scripts/lint-shell.sh --all                     # whole repo (hygiene sweep)
scripts/lint-shell.sh install.sh reorient.sh    # specific files
LINT_SEVERITY=style scripts/lint-shell.sh       # include style/info suggestions
scripts/lint-shell.sh install.sh -- -f diff | git apply   # apply ShellCheck's auto-fixes
scripts/lint-shell.sh -- -f gcc                 # file:line:col format for editors / CI
```

Exit: `0` clean · `1` findings or zsh syntax errors · `2` ShellCheck missing / bad usage.

### 4.4 Reading and fixing a finding

```
In scripts/gates/pr-14.sh line 23:
  no_match 'TOKEN=' $(git ls-files)
                    ^-------------^ SC2046 (warning): Quote this to prevent word splitting.
```

1. Look up the code: `https://www.shellcheck.net/wiki/SC2046`.
2. **Fix the code** whenever possible. The usual fixes in this repo:

| Code | Means | Fix |
|---|---|---|
| SC2086 | unquoted `$var` | `"$var"`; arrays `"${arr[@]}"` |
| SC2046 | unquoted `$(cmd)` | `mapfile -t files < <(cmd)` then `"${files[@]}"` |
| SC2155 | `local x=$(cmd)` hides cmd's exit code | `local x; x=$(cmd)` |
| SC2015 | `A && B \|\| C` isn't if/else | write the `if` |
| SC2164 | `cd dir` without a failure path | `cd dir \|\| exit` |
| SC2034 | variable appears unused | delete it, or see 4.6 if another file reads it |
| SC2154 | variable referenced but not assigned | assign it, or see 4.6 if a sourced file sets it |
| SC1091 | can't follow a `source` | add `# shellcheck source=path/to/file` above it |
| SC1017 | CRLF line endings | §1.5 |

3. Re-run `scripts/lint-shell.sh FILE` until clean.

### 4.5 zsh files

`zsh -n file.zsh` checks syntax only. For logic, the CLI has its bats suites
(`packages/cli/tests/bats`). Don't add `# shellcheck shell=bash` to a zsh file to force
linting: the findings would be about bash semantics, not zsh.

### 4.6 Suppressing a finding (rarely, and always with a reason)

Only when the code is right and ShellCheck can't see why, typically variables set or
read by *another* file:

```bash
# shellcheck disable=SC2034  # PR_* entries are read by scripts/pr.sh
```

* **Inline** (line above the statement) for a one-off.
* **File-wide**: directives placed before the first command apply to the whole file.
  The gate files use this for `SC2034,SC2154` because `lib.sh` defines what they read and
  `pr.sh` reads what they define.
* Never disable without the trailing `# reason`. Reviewers should reject bare disables.

### 4.7 Optional: lint before every commit

`.git/hooks/pre-commit` (not versioned; per clone):

```bash
#!/usr/bin/env bash
exec scripts/lint-shell.sh --changed HEAD
```

`chmod +x .git/hooks/pre-commit`. Bypass in an emergency with `git commit --no-verify`,
and expect gate 15 to catch it anyway.

---

## 5. Troubleshooting

### 5.1 A step FAILs

```
  ✖ FAIL  live: where msi/bind → operation (0s · log: .gates/logs/PR-09_live__where_msi_bind___operation.log)
```

1. The last 40 lines are printed inline; the whole log is at the path shown.
2. Re-run just that PR with output: `scripts/pr.sh gate 09 --only -v`.
3. Live steps: the API's own log is `.gates/logs/api-server.log`.
4. Run the underlying command by hand. Every step is a plain command in
   `scripts/gates/pr-NN.sh`; copy it.

### 5.2 A step SKIPs

The reason names the fix (`missing shellcheck`, `fastapi/uvicorn not installed - just
mvp-install`, `Postgres not on :55432 - just db-init`, `no DB user - export …`).
`scripts/pr.sh doctor` shows all of them at once. Skips are fine in the inner loop and
fatal under `--strict` (except the slow steps skipped by `--fast`).

### 5.3 "green but not complete — no pass marker written"

You ran with `--fast` or something skipped. Run `--strict`.

### 5.4 `start` refuses

| Message | Cause | Fix |
|---|---|---|
| `working tree not clean` | uncommitted changes | commit or `git stash` |
| `PR-NN gate is not green on HEAD` | previous PR's marker missing or stale (new commit, merge, edit) | `scripts/pr.sh gate NN --strict` on the current HEAD, or `--force` if you know why |
| `git am stopped` | patch drift against your branch | resolve conflicts, `git add`, `git am --continue`, then gate |

### 5.5 `finish` refuses

`no green --strict gate for this exact commit`: you committed or edited after gating.
Re-run `scripts/pr.sh gate NN --strict`.

### 5.6 Marker shows `stale` in `pr.sh list`

Expected after any commit, edit or merge. Re-gate on the current commit.

### 5.7 Live API "failed to start"

`.gates/logs/api-server.log` has the traceback. Usual causes: venv not active (gates use
`.venv/bin/python` when it exists, else `python3`), a broken `domain.json` (run
`validate_domain.py --all`), or the import error of an unfinished change.

### 5.8 DB steps fail rather than skip

Postgres answers but the run fails: check `OB_DB_USER`, `~/.pgpass` and that no other
session is connected to `ob_generic` (sandbox clones use it as a `TEMPLATE`; close psql
sessions or GUI clients). A 503 in the log means the API could not reach the database.

### 5.9 `scripts/pr.sh needs bash >= 4`

macOS system bash. `brew install bash`; the `#!/usr/bin/env bash` shebang picks it up
as long as Homebrew's bin precedes `/bin` in `PATH`.

### 5.10 Using an API you already run

`GATE_API_URL=http://127.0.0.1:8000 scripts/pr.sh gate 09` points live steps at it
instead of starting one. Steps that need a differently configured server (PR-10's
exec-enabled checks) then skip.

---

## 6. Command reference

| Command | Purpose |
|---|---|
| `scripts/pr.sh doctor` | toolchain report |
| `scripts/pr.sh list` | PRs + gate status |
| `scripts/pr.sh flow NN` | routine + smoke list for one PR |
| `scripts/pr.sh start NN [--patch F] [--force]` | branch for PR NN |
| `scripts/pr.sh gate NN [--fast] [--strict] [--only] [-v]` | run the gate |
| `scripts/pr.sh smoke NN` | manual checklist |
| `scripts/pr.sh finish NN [--push]` | push + open PR (requires strict green) |
| `scripts/lint-shell.sh [--changed [BASE] \| --all \| FILE…] [-- ARGS]` | ShellCheck / `zsh -n` |
| `just gate NN [flags]` · `just pr <cmd> NN` · `make gate PR=NN FLAGS=…` | shortcuts |

Environment knobs: `GATE_API_URL`, `LINT_SEVERITY`, `NO_COLOR`, `OB_DB_PORT`,
`OB_DB_USER`, `PY` (Python used by the gates).
