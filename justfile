# ─────────────────────────────────────────────────────────────────────────────
# justfile — onboarded task runner           https://github.com/casey/just
#
#   just                 list recipes
#   just install         clean install (idempotent): paths, shell wiring, launchers, adapters, self-test
#   just status          what is installed, which tenant/instance is active, is it healthy
#   just smoke           quick battery against the default tenant
#   just baseline        record a Baseline run (Flotilla + ISAR) with full provenance
#
# Nothing here hard-codes a path. ONBOARDED_DIR is this file's directory; the
# paths outside the repo come from ~/.onboarded/paths.conf (see docs/development/paths.md).
# msi-nav is no longer part of the workflow; its swap/diff harness survives only
# as the optional `legacy-*` recipes at the bottom.
# ─────────────────────────────────────────────────────────────────────────────

set shell := ["bash", "-uc"]

ONBOARDED_DIR := justfile_directory()
CONF          := env_var("HOME") + "/.onboarded/paths.conf"
# Default tenant: $OB_TENANT → paths.conf OB_DEFAULT_TENANT → flotilla (if generated) → generic
OB_TENANT     := `sh -c '[ -r "$HOME/.onboarded/paths.conf" ] && . "$HOME/.onboarded/paths.conf"; t="${OB_TENANT:-${OB_DEFAULT_TENANT:-}}"; [ -z "$t" ] && { [ -f packages/core/generated/flotilla/nav_maps.zsh ] && t=flotilla || t=generic; }; printf %s "$t"'`
MSI_NAV_DIR   := `sh -c '[ -r "$HOME/.onboarded/paths.conf" ] && . "$HOME/.onboarded/paths.conf"; printf %s "${MSI_NAV_DIR:-}"'`
BATS          := env_var_or_default("BATS", `command -v bats 2>/dev/null || echo bats`)
PROFILE       := ONBOARDED_DIR + "/packages/cli/src/ob_profile.zsh"
OB_GENERATED  := ONBOARDED_DIR + "/packages/core/generated/" + OB_TENANT
PY            := "python3"

# One non-interactive zsh with onboarded loaded for OB_TENANT (no ~/.zshrc involved).
OB_ZSH := 'OB_TENANT=' + OB_TENANT + ' zsh -f -c'

default:
    @just --list --unsorted

# ─────────────────────────────────────────────────────────────────────────────
# INSTALL
# ─────────────────────────────────────────────────────────────────────────────

# Clean, idempotent install. Options pass through, e.g. just install --tenant flotilla
install *ARGS:
    @{{ONBOARDED_DIR}}/install.sh {{ARGS}}

# Verify an install without changing anything
install-check:
    @{{ONBOARDED_DIR}}/install.sh --check

# Remove shell wiring and launchers (keeps instances, databases and workspace)
uninstall *ARGS:
    @{{ONBOARDED_DIR}}/install.sh --uninstall {{ARGS}}

# Foundational paths: check | where | fix --apply | restore <id> --apply
paths *ARGS:
    @{{PY}} {{ONBOARDED_DIR}}/packages/core/scripts/ob_paths.py {{ARGS}}

# ─────────────────────────────────────────────────────────────────────────────
# STATUS / GENERATION / SHELL
# ─────────────────────────────────────────────────────────────────────────────

status:
    @echo ""
    @echo "  ── onboarded ─────────────────────────────────────────────────────"
    @echo "  Path:     {{ONBOARDED_DIR}}"
    @[ -d "{{ONBOARDED_DIR}}/.git" ] && echo "  Commit:   $(git -C {{ONBOARDED_DIR}} log -1 --format='%h %s' 2>/dev/null)" || true
    @echo "  Tenant:   {{OB_TENANT}}   (active instance: $(cat ~/.onboarded/active 2>/dev/null || echo none))"
    @[ -f "{{OB_GENERATED}}/nav_maps.zsh" ] && echo "  Adapters: ✔ generated" || echo "  Adapters: ✗ missing — run: just generate"
    @command -v onboarded >/dev/null 2>&1 && echo "  Launcher: ✔ $(command -v onboarded)" || echo "  Launcher: ✗ not on PATH — run: just install"
    @{{PY}} {{ONBOARDED_DIR}}/packages/core/scripts/ob_paths.py check 2>/dev/null | tail -2 | sed 's/^/  /'
    @echo ""

# Validate + generate adapters for one tenant (default: the current tenant)
generate TENANT=OB_TENANT:
    @cd {{ONBOARDED_DIR}} && {{PY}} packages/core/scripts/validate_domain.py --tenant {{TENANT}}
    @cd {{ONBOARDED_DIR}} && {{PY}} packages/core/scripts/generate_adapters.py --tenant {{TENANT}}

generate-all:
    @cd {{ONBOARDED_DIR}} && {{PY}} packages/core/scripts/validate_domain.py --all
    @cd {{ONBOARDED_DIR}} && {{PY}} packages/core/scripts/generate_adapters.py --all

# Interactive zsh with onboarded loaded and nothing from your ~/.zshrc
shell:
    @d="$(mktemp -d)"; printf 'export OB_TENANT=%s\nsource "%s"\necho "  ✔ onboarded ready (tenant %s)"\n' "{{OB_TENANT}}" "{{PROFILE}}" "{{OB_TENANT}}" > "$d/.zshrc"; ZDOTDIR="$d" zsh -i || true; rm -rf "$d"

# Run one command through onboarded. Usage: just run "onboarded where schedule_mission"
run CMD:
    @{{OB_ZSH}} 'source "{{PROFILE}}"; {{CMD}}'

# ─────────────────────────────────────────────────────────────────────────────
# TESTS
# ─────────────────────────────────────────────────────────────────────────────

# Quick battery (3 items per map) against the current tenant
smoke:
    @zsh {{ONBOARDED_DIR}}/packages/cli/tests/battery/ob_battery.zsh --tenant {{OB_TENANT}} --max 3 --quiet

# Shell suites + DBA unit tests
test:
    @{{BATS}} {{ONBOARDED_DIR}}/packages/cli/tests/bats/nav/test_nav_generic.bats --formatter tap
    @{{BATS}} {{ONBOARDED_DIR}}/packages/cli/tests/bats/nav/test_nav_msi.bats --formatter tap
    @{{BATS}} {{ONBOARDED_DIR}}/packages/cli/tests/bats/scan/test_scan_msi.bats --formatter tap
    @just dba-test

# Full command battery. Usage: just battery --tenant flotilla --db --dba --instance
battery *ARGS:
    @zsh {{ONBOARDED_DIR}}/packages/cli/tests/battery/ob_battery.zsh {{ARGS}}

# Record a Baseline run with provenance. Usage: just baseline   (or: just baseline --no-db)
baseline *ARGS:
    @{{ONBOARDED_DIR}}/benchmarks/baseline-v1/record.sh {{ARGS}}

# ─────────────────────────────────────────────────────────────────────────────
# LOCAL DATABASE + DBA ENGINE  (docs/development/local-db.md)
# ─────────────────────────────────────────────────────────────────────────────

# Start Postgres in Docker; roles, ob_generic, demo data (idempotent)
db-init:
    @{{ONBOARDED_DIR}}/deploy/local/db/init-local-db.sh

db-up:
    @docker compose -f {{ONBOARDED_DIR}}/deploy/local/db/docker-compose.db.yml --env-file {{ONBOARDED_DIR}}/deploy/local/db/.env up -d

db-down:
    @docker compose -f {{ONBOARDED_DIR}}/deploy/local/db/docker-compose.db.yml --env-file {{ONBOARDED_DIR}}/deploy/local/db/.env down

# DANGER: deletes the local database volume
db-reset:
    @docker compose -f {{ONBOARDED_DIR}}/deploy/local/db/docker-compose.db.yml --env-file {{ONBOARDED_DIR}}/deploy/local/db/.env down -v
    @just db-init

# DBA engine passthrough. Usage: just dba ping  /  just dba run 2001 dryrun
dba *ARGS:
    @cd {{ONBOARDED_DIR}} && OB_REPO_ROOT={{ONBOARDED_DIR}} PYTHONPATH=packages/dba/src \
        $([ -x packages/dba/.venv/bin/python ] && echo packages/dba/.venv/bin/python || echo python3) \
        -m dba --tenant {{OB_TENANT}} {{ARGS}}

dba-test:
    @cd {{ONBOARDED_DIR}}/packages/dba && \
        $([ -x .venv/bin/python ] && echo .venv/bin/python || echo python3) -m pytest -q

# ─────────────────────────────────────────────────────────────────────────────
# INSTANCES  (docs/development/instances.md)
# ─────────────────────────────────────────────────────────────────────────────

# ob-instance passthrough. Usage: just i list  /  just i doctor flotilla
i *ARGS:
    @{{PY}} {{ONBOARDED_DIR}}/packages/core/scripts/ob_instance.py {{ARGS}}

# ─────────────────────────────────────────────────────────────────────────────
# PORTAL / NX
# ─────────────────────────────────────────────────────────────────────────────

portal-start:
    @cd {{ONBOARDED_DIR}} && npx nx serve @onboarded/portal

portal-start-generic:
    @cd {{ONBOARDED_DIR}} && npx nx serve @onboarded/portal --configuration=generic

portal-build:
    @cd {{ONBOARDED_DIR}} && npx nx build @onboarded/portal

portal-build-prod:
    @cd {{ONBOARDED_DIR}} && npx nx build @onboarded/portal --configuration=production

portal-test:
    @cd {{ONBOARDED_DIR}} && npx nx test @onboarded/portal

portal-lint:
    @cd {{ONBOARDED_DIR}} && npx nx lint @onboarded/portal

portal-typecheck:
    @cd {{ONBOARDED_DIR}} && npx nx typecheck @onboarded/portal

nx-build:
    @cd {{ONBOARDED_DIR}} && npx nx run-many -t build

nx-test:
    @cd {{ONBOARDED_DIR}} && npx nx run-many -t test

nx-lint:
    @cd {{ONBOARDED_DIR}} && npx nx run-many -t lint

nx-affected:
    @cd {{ONBOARDED_DIR}} && npx nx affected -t build test lint typecheck

nx-graph:
    @cd {{ONBOARDED_DIR}} && npx nx graph

nx-reset:
    @cd {{ONBOARDED_DIR}} && npx nx reset

# ─────────────────────────────────────────────────────────────────────────────
# LEGACY — msi-nav reference only. Not part of the build, tests or baseline.
# Needs MSI_NAV_DIR in ~/.onboarded/paths.conf (obpaths fix --msi-nav PATH --apply).
# ─────────────────────────────────────────────────────────────────────────────

_need-msi-nav:
    @[ -n "{{MSI_NAV_DIR}}" ] && [ -d "{{MSI_NAV_DIR}}" ] || { echo "  legacy recipes need MSI_NAV_DIR (obpaths fix --msi-nav PATH --apply)"; exit 1; }

# Snapshot msi-nav file hashes (reference only)
legacy-snapshot: _need-msi-nav
    @find {{MSI_NAV_DIR}} -type f \( -name "*.zsh" -o -name "*.sh" -o -name "*.py" -o -name "*.json" \) \
        | sort | xargs sha256sum > {{ONBOARDED_DIR}}/.msi-nav-snapshot.sha
    @echo "  ✔  $(wc -l < {{ONBOARDED_DIR}}/.msi-nav-snapshot.sha | tr -d ' ') files recorded"

# Confirm msi-nav has not changed since the snapshot
legacy-verify: _need-msi-nav
    @find {{MSI_NAV_DIR}} -type f \( -name "*.zsh" -o -name "*.sh" -o -name "*.py" -o -name "*.json" \) \
        | sort | xargs sha256sum | diff -q {{ONBOARDED_DIR}}/.msi-nav-snapshot.sha - >/dev/null \
        && echo "  ✔  msi-nav unchanged" || echo "  ✗  msi-nav changed since snapshot"

# Compare one command between msi-nav and onboarded (msi tenant). Usage: just legacy-diff "msi where bind"
legacy-diff CMD: _need-msi-nav
    @zsh -f -c 'source "{{MSI_NAV_DIR}}/msi_domain.zsh" 2>/dev/null; source "{{MSI_NAV_DIR}}/msi_nav.zsh" 2>/dev/null; {{CMD}}' > /tmp/ob_diff_a.txt 2>&1 || true
    @OB_TENANT=msi zsh -f -c 'source "{{PROFILE}}"; {{CMD}}' > /tmp/ob_diff_b.txt 2>&1 || true
    @diff -u /tmp/ob_diff_a.txt /tmp/ob_diff_b.txt || true
