# PR workflow — the routine for every MVP PR

> Step-by-step operations, tool setup, ShellCheck and troubleshooting:
> `docs/development/runbook-pr-gates.md`. Check your machine first with `scripts/pr.sh doctor`.

Every PR in `MVP_ROADMAP.md` §4 goes through the same seven steps, driven by
`scripts/pr.sh`. A PR is "done" only when its **gate is green in `--strict` mode on the
exact commit you push**, and its **manual smoke** list is ticked in the PR description.
The next PR cannot `start` until then.

```
 start ──► build ──► gate --fast (loop) ──► gate --strict ──► smoke ──► finish ──► merge
   │                    seconds                 full, no skips    human     push + PR
   └─ refuses unless the previous PR's gate is green on HEAD
```

## The commands

| Step | Command | What it does |
|---|---|---|
| – | `scripts/pr.sh doctor` | which tools are installed and which gates need them |
| 0 | `scripts/pr.sh list` | every PR this checkout knows, branch, gate status (`green` / `stale` / `-`) |
| 1 | `scripts/pr.sh flow NN` | prints this routine for PR NN with its branch, base and smoke list |
| 2 | `scripts/pr.sh start NN [--patch PR-NN.patch]` | clean-tree check → previous gate green? → create/switch branch → optional `git am --3way` |
| 3 | `scripts/pr.sh gate NN --fast` | regression of earlier gates (fast) + this PR's checks, skipping slow steps — the inner loop |
| 4 | `scripts/pr.sh gate NN --strict` | everything; a step skipped for a missing tool **fails**. Green writes `.gates/NN.pass` |
| 5 | `scripts/pr.sh smoke NN` | the checks a human has to look at (browser, terminal output, DB state) |
| 6 | `scripts/pr.sh finish NN [--push]` | refuses unless `.gates/NN.pass` matches HEAD + clean tree; pushes and runs `gh pr create --base <previous branch>` with the gate result and smoke checklist as the body |
| 7 | merge | after review, on the merged branch: `scripts/pr.sh gate NN --strict` again (a merge is a new commit, so the marker is `stale` and `start` of the next PR refuses until the merged result is green) |

Shortcuts: `just gate NN [flags]`, `just pr <cmd> NN`, `make gate PR=NN`.

Exit codes: `0` green · `1` a step failed · `2` usage or precondition (dirty tree, gate not green).

## How a gate works

* Each PR owns `scripts/gates/pr-NN.sh` with `gate_NN` (automated steps) and `smoke_NN`
  (manual list). The gate file ships **in the same PR** as the feature it guards, so applying
  archive NN also gives you its gate.
* `gate NN` first re-runs every earlier gate in fast mode (**regression**), then NN in full.
  Use `--only` to skip regression while iterating.
* Steps never abort the run; you get a full PASS / FAIL / SKIP table and, for each failure,
  the tail of its log (full logs in `.gates/logs/`).
* **Live steps** start the real API on a random port (`python -m onboarded_api`) and hit it
  with `curl`; they need `fastapi` + `uvicorn` (`just mvp-install`). Database steps run only
  when Postgres answers on `:55432` (`just db-init`) and a DB user is set
  (`export OB_DB_PORT=55432 OB_DB_USER=ob_dba`, password via `ob_instance.py pgpass`).
* **Skips are explicit.** Missing `tsc`, `node_modules`, `fastapi`, Docker or Postgres →
  SKIP with the reason and the fix. `--strict` turns those into failures, which is why
  `finish` requires a strict pass.
* The pass marker is a fingerprint of `HEAD` + tracked changes; any new commit or edit
  makes it `stale`.

## What each gate checks

| PR | Automated (gate) | Manual (smoke) |
|---|---|---|
| **00** roadmap | docs present; every repo path named in the docs exists (or is listed in `scripts/gates/planned-paths.txt`); gate scripts parse; shellcheck | rotate Nx token; `pr.sh list/flow` sane |
| **09** API core | `validate_domain --all`; TS snapshots fresh (regenerate → no git diff); shared types strict typecheck; API service + HTTP tests; **live**: `/health` ok with 3 tenants, `/docs`, camelCase domain, 404 problem+json, `where`, inline scan → exitCode 1, path outside roots → 403 | `/docs` by hand; reload after a domain edit; broken domain → `degraded` |
| **10** API DBA | dba unit tests; API DBA tests; **live**: tickets, runbook, run refused while exec off (403); second server with exec on: `fix` without / with wrong confirm → 428; **db** (after `just db-init`): generic 1001 diagnostic live + dryrun in a sandbox clone | sandbox clone created + dropped; confirmed `fix` in sandbox; DB down → 503 |
| **11** admin CLI | CLI tests; every exit code of the contract (0, 1, 4, 5, 6, 7) via `--local`; **live parity**: `--local --json` ≡ `--api --json` for tenants / where / tickets / status; API-mode scan + refused run | readability, `NO_COLOR`, automatic local fallback |
| **12** portal build | snapshots fresh; every path in `project.json` exists; every route has a feature folder; no `*ngIf/*ngFor`, no `standalone: true`, no snake_case domain access; **slow**: `nx build` for generic / msi / flotilla + unit tests | per-tenant branding and terminology; empty collections hidden; filters |
| **13** portal live | `HttpClient` only in `core/services`; no hard-coded API host; interceptor registered; proxy → :8000; confirm header name matches the API; API contract types exported; **slow**: production build; **live**: every endpoint the portal calls answers | API dot on/off; Live scan; tickets browse/run; typed confirm; instances |
| **14** dev stack | `.env` untracked + ignored; no Nx token in tracked files; compose YAML parses; `make`/`just` MVP targets exist; full `make mvp-test`; `docker compose config`; **slow**: `docker compose up --build` → portal :4200 serves SPA and proxies `/api` | README quick start on a fresh clone; `just mvp-up`; token rotated; acceptance checklist |
| **15** shell lint | `.shellcheckrc`; every bash script parses; no CRLF in shell files; `.gitattributes` pins LF; ShellCheck on PR tooling and on every shell file changed vs master; `zsh -n` on zsh files; `pr.sh doctor` runs; runbook present | `doctor` all ✔; `lint-shell.sh --all` triage; editor extension agrees |
| **16** entry points | every `src/` dir is a package; importing `pkg.__main__` doesn't run it; `python -m <pkg> --help` for dba / api / admin / feedback; `__version__` == pyproject; console scripts resolve; API services import without FastAPI; feedback telemetry round-trip; `suggest` exits 3 | `--help`/`--version` of each installed script; `ob_telemetry_show` from zsh |
| **17** lint findings | generic `nav_maps_db.zsh` only in `+=( "k" "v" )` form (10 entries); `validate_domain` unknown tenant → message + exit 1; ruff rules pinned and clean; **ShellCheck + `zsh -n` on the whole repo** | `lint-shell.sh --all` clean on your machine; generic DB maps load in zsh |

## Worked example (PR-11)

```bash
scripts/pr.sh gate 10 --strict                # previous PR must be green on HEAD
scripts/pr.sh start 11 --patch ~/Downloads/pr-11/PR-11.patch
scripts/pr.sh gate 11 --fast                  # iterate until green
scripts/pr.sh gate 11 --strict                # full run, writes .gates/11.pass
scripts/pr.sh smoke 11                        # do the manual checks
scripts/pr.sh finish 11 --push                # push + gh pr create --base feat/api-dba
```

## In CI (plan PR-7)

One job per PR number: `just mvp-install && scripts/pr.sh gate NN --strict`.
`--fast --strict` is "strict, except the slow steps" (fast-mode skips never fail), so a
runner without Docker or `node_modules` can run that, with a separate job for the slow
steps where the tooling exists.
