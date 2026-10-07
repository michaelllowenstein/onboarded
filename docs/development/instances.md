# Instances — running onboarded against many codebases

An **instance** is one onboarded deployment against one client codebase:

```
instance = tenant     packages/core/tenants/<slug>/   domain.json, scripts/<ticket>/
         + templates  templates/<slug>/                sql templates, ticket scaffolds
         + manifest   instances/<slug>/                instance.json, SCORECARD.md, FINDINGS.md
         + workspace  $OB_WORKSPACE/<slug>/            repos/ runs/ notes/ dumps/
         + database   ob_<slug> on the local Postgres
         + env        ~/.onboarded/instances/<slug>.env
```

Tool: `packages/core/scripts/ob_instance.py` (alias `obi` in zsh, `just i …`).
Stdlib-only Python; needs git, and psql or the `onboarded-pg` container.

## Principles

1. **Isolation.** Each instance has its own database, env file, ticket state
   (`~/.onboarded/<slug>/`) and clone directory. Switching instance never
   leaves the previous one's variables behind.
2. **Reproducibility.** Client repos are pinned to commits in `instance.json`;
   a finding is only meaningful against a known commit.
3. **Confidentiality by construction.** A *confidential* instance's tenant,
   templates and manifest physically live in the workspace and are symlinked
   into the repo; git exclude rules and a pre-commit guard keep them, and their
   generated adapters, out of commits.
4. **Measured, not anecdotal.** Every instance keeps a SCORECARD (coverage,
   benchmark, DBA rehearsal) and a FINDINGS log of engine gaps, so instances can
   be compared and the engine improved from evidence.

## Classification

| | public | confidential |
|---|---|---|
| Use for | open-source test codebases | employer / client codebases |
| Tenant + templates + manifest | committed | workspace overlay, symlinked, git-excluded |
| Generated adapters | committed | git-excluded |
| Guard | — | `obi guard` pre-commit hook blocks them even with `git add -f` |

`obi new <slug> --confidential` sets this up. For an existing tenant:
`obi adopt <slug> --confidential`, then follow the printed steps to untrack it and
`obi overlay <slug>` to move it into the workspace. Exclude rules do not remove
anything from earlier commits.

## Lifecycle

| State | Exit criteria |
|---|---|
| `planned` | `obi new` done; repos listed in the manifest |
| `cloned` | `obi clone` done; commits pinned and manifest committed |
| `derived` | domain.json derived (docs/development/derivation.md steps 1–8); `obi check-paths` all resolve |
| `generated` | `obi generate` clean; `obi doctor` healthy |
| `benchmarked` | SCORECARD sections 2–4 filled; at least one DBA ticket rehearsed end to end |
| `archived` | findings rolled up; database dropped (`obi db-drop --yes`) or kept read-only |

Move between states with `obi status <slug> <state>` (`clone` and `generate` advance it automatically).

## Daily use

```bash
obi list                      # ▶ marks the active instance
obuse fineract                # switch the current zsh: tenant, repos, DB
onboarded where disburse      # nav against fineract's clones
onboarded dba run 3001 dryrun # DBA against ob_fineract
obi doctor                    # every instance: adapters fresh, repos at pin, DB reachable, nothing leaked
```

A new shell picks up the active instance automatically when `OB_TENANT` is
not set (the dispatcher reads `~/.onboarded/active`). Setting `OB_TENANT`
explicitly, as the msi-nav swap harness does, still wins.

## Getting data into an instance database

Pick the first that works for the codebase:

1. **Migrations straight into `ob_<slug>`.** Point the project's own migration
   tool at the instance DB (EF Core `dotnet ef database update`, Alembic,
   `rails db:prepare`, Liquibase…), connecting as `ob_dba`.
2. **Run the app on its own compose, then dump and load.** Bring the project up
   the way its README says, create a few records through its API/UI, then
   `pg_dump -Fc` its database and `obi db-load <slug> file.dump`.
3. **Hand-written seed SQL** under `$OB_WORKSPACE/<slug>/dumps/`, loaded with `obi db-load`.

Always load as `ob_dba` (`db-load` does) so `ob_reader` read grants apply to the new tables.

## Comparing instances

After each instance reaches `benchmarked`, copy its "engine gaps" section into
a dated line in `docs/reports/` (one file per quarter is enough). Gaps that recur
across two or more instances are the engine backlog; gaps unique to one
instance are tenant data.
