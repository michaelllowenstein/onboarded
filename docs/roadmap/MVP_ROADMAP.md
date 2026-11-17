# MVP Roadmap — Admin CLI · REST API · Web Portal

**Goal:** a usable MVP where an operator can, for any tenant (`generic`, `msi`, `flotilla`):

1. browse the domain (operations, statuses, glossary, scan rules, queues, portals) in the **portal**,
2. ask the same questions from a terminal with **`ob-admin`**,
3. scan code with the tenant's rules (portal paste-box, CLI on local paths),
4. inspect DBA tickets and rehearse them safely (sandbox), from either surface,

all backed by one **REST API** that serves the same data the portal compiles in.

This continues the scratch-build plan (`onboarded-scratch-build-plan.md`, PR-1…PR-8) as
**PR-9…PR-14**. Each PR ships as an overlay archive (see *Applying the archives*) and
carries its own **gate** — the routine every PR must pass before the next one starts is in
[`PR_WORKFLOW.md`](PR_WORKFLOW.md) (`scripts/pr.sh start → gate → smoke → finish`).

---

## 1. Where things stood (baseline export)

| Package | State at baseline | Notes |
|---|---|---|
| `core` | **Mature** | 3 valid tenants, generator, validator, `ob_instance.py`, `ob_paths.py` |
| `cli` (zsh/ps1) | **Mature** | dispatcher, nav/scan engines, bats suites |
| `dba` | **Mature** | Postgres + MSSQL runner, sandbox clones, 34 passing tests |
| `shared` | Partial | types existed, but snapshots were stale hand copies (see F1, F2) |
| `portal` | **Would not build** | 2 of 8 routes; config pointed at files that don't exist (F3) |
| `api` | Empty (`.gitkeep`) | fully specified in plan PR-5, never scaffolded |
| `admin-cli` | Empty (`.gitkeep`) | plan PR-8 |
| `feedback` | Stubs | telemetry store + tests only; out of MVP scope |
| `deploy` | Placeholders | one-line Dockerfiles / nginx / k8s |

## 2. Findings

### Fixed in this sequence

| # | Finding | Impact | Fixed in |
|---|---|---|---|
| F1 | `generate_adapters.py` defined `emit_tenant_ts()` but never called it; `--ts-only` was ignored | TS snapshots never regenerated; `generic.ts` carried MSI repo config; no `flotilla.ts` | PR-9 |
| F2 | TS types are camelCase (`brandName`, `scanRules`, `seeAlso`) but snapshots were raw snake_case JSON cast `as unknown as TenantDomain` | portal brand blank, scan rules `undefined` at runtime — the compiler couldn't see it | PR-9 (`domain_view.py`) |
| F3 | portal `project.json` replaced `src/environments/*` (files live in `src/envs/*`), referenced `styles.scss` (file is `.css`), `tsconfig` path for `@onboarded/shared` resolved outside the repo, `types: ["node"]` without `@types/node` | build fails | PR-12 |
| F4 | `env.ts` declared `tenant: 'msi'` but imported the generic snapshot | wrong tenant shown | PR-12 |
| F5 | shell template used `*ngIf` without `CommonModule` under `strictTemplates` | template compile error | PR-12 |
| F6 | `missing_cancellation_token` rule (`public async Task`) matched methods that *do* take a token — it fired on the "clean" fixture | false positives | PR-9 |
| F7 | `generic` has no `queues`; `DomainService.getQueues()` would throw | crash on route | PR-9 (view always has every collection) |
| F8 | root `.env` (NX Cloud token) tracked and not ignored | secret in history | PR-14 (untracked + ignored) — **rotate the token** |
| F9 | `tsconfig.base.json` uses `baseUrl`, removed in TypeScript 6 | breaks on TS 6 upgrade | PR-12 (relative `paths`, works on 5.9 and 6) |
| F10 | Scan exclude globs ignored directory boundaries: `**/fixtures/**` also excluded `scan_fixtures/…`, `**/tests/**` excluded `unit_tests/…` | real findings silently dropped | PR-9 (glob → regex with segment boundaries). *Caught by the PR-11 gate's local-vs-API parity check.* |
| F11 | `ob-admin --local` only worked when run inside the repo; scan paths were relative to the scanned folder, so `**/tests/**` never applied locally | CLI unusable on other projects; local ≠ API results | PR-11 (repo located via the installed package; paths relative to the current directory) |

### Open — not blocking the MVP

| # | Finding | Recommendation |
|---|---|---|
| O1 | zsh scan engine uses `grep -E` (ERE). Rules with look-aheads (`todo_comment`, and now `missing_cancellation_token`) error silently there (`2>/dev/null`) while the API/CLI (Python `re`) honour them | switch the engine to `rg` → `grep -P` fallback and declare patterns PCRE in `tenant.schema.json` |
| O2 | `package-lock.json` is stale (no resolved `typescript`, mixed versions) | `rm package-lock.json && npm install`, commit |
| O3 | `deploy/local/db/.env` (local Postgres passwords) appears in the export | confirm it is untracked; rotate if it was ever pushed |
| O4 | Hand-written API types in `shared` | generate from `/openapi.json` with `openapi-typescript` once the API settles |
| O5 | API has no auth | fine for localhost MVP; add a bearer token / reverse-proxy auth before any shared deploy |

## 3. Decisions (and where they differ from the scratch plan)

| Topic | Plan said | MVP does | Why |
|---|---|---|---|
| Tenant selection in API | `X-Onboarded-Tenant` header + middleware | **path**: `/api/v1/tenants/{slug}/…` | cacheable, curl-able, self-describing; no hidden default tenant |
| Admin CLI | Python Typer `ob` **and** TypeScript `ob-admin` | **one** stdlib Python `ob-admin`, API + `--local` backends | one code path for results; matches `ob-dba`/`ob_instance.py`; no new deps |
| Domain shape | API returned raw `domain.json` | API and portal both use `domain_view.to_view()` (camelCase) | one contract, enforced by a parity test |
| Scan endpoint | scanned any server path | inline `content`, or `paths` inside `OB_API_SCAN_ROOTS` only | arbitrary server-side file reads are a vulnerability |
| SQL over HTTP | not in plan | off by default (`OB_API_DBA_EXEC`), sandbox default, exact-echo confirm header for `fix`/`rollback` | same safety bar as the CLI's `--yes` |
| React islands | in PR-4 | **deferred** | not needed for MVP; Custom Element boundary still the plan |
| Portal API base | `http://localhost:8000` | `''` + dev proxy / nginx | no CORS, no per-environment URLs |

## 4. PR sequence

| PR | Branch | Package(s) | Scope | Test gate | Archive |
|---|---|---|---|---|---|
| 0 | `docs/mvp-roadmap` | docs, scripts | this roadmap, `PR_WORKFLOW.md`, `scripts/pr.sh` + gate library | `scripts/pr.sh gate 00 --strict` | `docs` |
| 9 | `feat/api-core` | core, shared, **api** | `domain_view.py`; generator writes TS snapshots; FastAPI app: health, tenants, domain, where, statuses, glossary, scan-rules, sandboxed scan, reload; problem+json errors | `scripts/pr.sh gate 09 --strict` (42 service tests incl. view == snapshot parity, 7 live API checks) | `api-v0.1` |
| 10 | `feat/api-dba` | **api** | tickets, runbooks, script source, gated run, instances | `gate 10` (54 API tests; exec-off 403, confirm 428; with `just db-init`: generic 1001 diagnostic + sandbox dryrun) | `api-v0.2` |
| 11 | `feat/admin-cli` | **admin-cli** | `ob-admin` (15 commands), exit-code contract, API/local backends | `gate 11` (20 tests, every exit code, local ≡ API parity) | `admin-cli-v0.1` |
| 12 | `fix/portal-build` | **portal**, root tsconfig | build config fixes, per-tenant configs, all 6 build-time pages | `gate 12` (config/route/template lint + 3 tenant builds) | `portal-v0.1` |
| 13 | `feat/portal-api` | **portal** | interceptor + `ApiService`, Live scan, DBA tickets (run), Instances, API status | `gate 13` (HTTP boundary lint, build, live endpoints) + smoke | `portal-v0.2` |
| 14 | `feat/mvp-devstack` | deploy, root | Dockerfiles, nginx, compose, `just`/`make` recipes, README, `.env` hygiene | `gate 14` (secrets, compose, `make mvp-test`, compose e2e) | `devstack-v0.1` |

Merge order is linear (each branch is cut from the previous). PR-11 needs only PR-9/10;
PR-12 needs only PR-9 (snapshots) — they can be reviewed in parallel.

### MVP acceptance checklist

- [ ] `just mvp-install && just mvp-test` green on a clean clone
- [ ] `just api` → `/health` = `ok`, 3 tenants; `/docs` renders
- [ ] `just admin -t msi where bind` prints controllers + code path; `just admin scan <fixtures>` exits `1`
- [ ] `npx nx build @onboarded/portal -c flotilla` succeeds; `just portal` shows Flotilla terminology
- [ ] Portal: Live scan finds the ViolationService fixture issues; API indicator green
- [ ] With `just db-init` + `OB_API_DBA_EXEC=1 just api`: run `generic:1001/dryrun` in sandbox from portal and CLI (`flotilla:2001` additionally needs the Flotilla schema loaded into `ob_flotilla`)
- [ ] `fix` without confirmation is refused (portal button disabled; CLI exit 7; API 428)
- [ ] `just mvp-up` → portal on :4200 talks to the API container

## 5. Applying the archives

Each archive is an **overlay** (paths relative to the repo root) containing:

* the PR's added/changed files — **including its gate**, `scripts/gates/pr-NN.sh`,
* `PR-NN.patch` — the same change as a `git format-patch` mailbox (carries the commit message),
* `PR_NOTES.md` — scope, the PR's routine, files touched; `DELETED.txt` — files the PR removes.

Apply PR-00 by hand once (it brings `scripts/pr.sh`); from then on every PR follows the
routine in [`PR_WORKFLOW.md`](PR_WORKFLOW.md):

```bash
cd ~/develop/product/onboarded && git checkout master && git pull
git checkout -b docs/mvp-roadmap && git am --3way PR-00.patch
scripts/pr.sh gate 00 --strict && scripts/pr.sh finish 00 --push

scripts/pr.sh start 09 --patch PR-09.patch     # refuses unless PR-00 is green on HEAD
scripts/pr.sh gate 09 --strict
scripts/pr.sh smoke 09
scripts/pr.sh finish 09 --push                 # … then 10, 11, 12, 13, 14 the same way
```

If `git am` stops on drift: resolve, `git add`, `git am --continue`, then gate.
Without git: unzip the overlay over the tree and remove the files in `DELETED.txt`.
`onboarded-mvp-full.zip` is the final tree (all PRs applied) for a quick look.

## 6. After the MVP

1. **CI** (plan PR-7): one job per PR number running `scripts/pr.sh gate NN --strict` after `just mvp-install` (the gates already include stale-snapshot, secret and parity checks).
2. Close O1 (scan engine PCRE) and O2 (lockfile).
3. OpenAPI-generated client types (O4); portal unit tests for `DomainService` and the interceptor.
4. Auth for any non-localhost deploy (O5); k8s manifests (plan PR-6).
5. React islands (Glossary search / scan dashboard) behind the Custom Element boundary.
6. `feedback` package: wire telemetry from `ob-admin` and the API into the suggestion engine.