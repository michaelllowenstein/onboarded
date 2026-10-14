# ─────────────────────────────────────────────────────────────────────────────
# Makefile — onboarded core targets (mirror of the justfile for machines without `just`)
#
#   make install         clean, idempotent install (paths, shell wiring, launchers, adapters, self-test)
#   make status          install health + current tenant
#   make smoke           quick battery against the current tenant
#   make test            shell suites + DBA unit tests
#   make baseline        record a Baseline run (Flotilla + ISAR)
#   make paths ARGS="fix --apply"
#
# ONBOARDED_DIR is this Makefile's own directory — never a hard-coded path, and a
# stale exported ONBOARDED_DIR is ignored. Paths outside the repo come from
# ~/.onboarded/paths.conf (docs/development/paths.md). msi-nav is not used here;
# its legacy recipes live only in the justfile (legacy-*).
# ─────────────────────────────────────────────────────────────────────────────

ONBOARDED_DIR  := $(patsubst %/,%,$(dir $(abspath $(lastword $(MAKEFILE_LIST)))))
-include $(HOME)/.onboarded/paths.conf
OB_TENANT      ?= $(or $(OB_DEFAULT_TENANT),$(if $(wildcard $(ONBOARDED_DIR)/packages/core/generated/flotilla/nav_maps.zsh),flotilla,generic))
BATS           ?= $(shell command -v bats 2>/dev/null || echo bats)
PY             ?= python3
DBA_PY         := $(if $(wildcard $(ONBOARDED_DIR)/packages/dba/.venv/bin/python),$(ONBOARDED_DIR)/packages/dba/.venv/bin/python,$(PY))
COMPOSE        := docker compose -f $(ONBOARDED_DIR)/deploy/local/db/docker-compose.db.yml --env-file $(ONBOARDED_DIR)/deploy/local/db/.env

.PHONY: help install install-check uninstall status generate generate-all smoke test battery baseline \
        paths db-init db-up db-down dba dba-test i

help:
	@echo "  ONBOARDED_DIR=$(ONBOARDED_DIR)  OB_TENANT=$(OB_TENANT)"
	@echo "  install install-check uninstall status generate generate-all smoke test"
	@echo "  battery ARGS=..  baseline ARGS=..  paths ARGS=..  db-init db-up db-down  dba ARGS=..  dba-test  i ARGS=.."

install:
	@$(ONBOARDED_DIR)/install.sh $(ARGS)

install-check:
	@$(ONBOARDED_DIR)/install.sh --check

uninstall:
	@$(ONBOARDED_DIR)/install.sh --uninstall $(ARGS)

status:
	@$(ONBOARDED_DIR)/install.sh --check

generate:
	@cd $(ONBOARDED_DIR) && $(PY) packages/core/scripts/validate_domain.py --tenant $(OB_TENANT)
	@cd $(ONBOARDED_DIR) && $(PY) packages/core/scripts/generate_adapters.py --tenant $(OB_TENANT)

generate-all:
	@cd $(ONBOARDED_DIR) && $(PY) packages/core/scripts/validate_domain.py --all
	@cd $(ONBOARDED_DIR) && $(PY) packages/core/scripts/generate_adapters.py --all

smoke:
	@zsh $(ONBOARDED_DIR)/packages/cli/tests/battery/ob_battery.zsh --tenant $(OB_TENANT) --max 3 --quiet

test:
	@$(BATS) $(ONBOARDED_DIR)/packages/cli/tests/bats/nav/test_nav_generic.bats --formatter tap
	@$(BATS) $(ONBOARDED_DIR)/packages/cli/tests/bats/nav/test_nav_msi.bats --formatter tap
	@$(BATS) $(ONBOARDED_DIR)/packages/cli/tests/bats/scan/test_scan_msi.bats --formatter tap
	@$(MAKE) --no-print-directory dba-test

battery:
	@zsh $(ONBOARDED_DIR)/packages/cli/tests/battery/ob_battery.zsh $(ARGS)

baseline:
	@$(ONBOARDED_DIR)/benchmarks/baseline-v1/record.sh $(ARGS)

paths:
	@$(PY) $(ONBOARDED_DIR)/packages/core/scripts/ob_paths.py $(ARGS)

db-init:
	@$(ONBOARDED_DIR)/deploy/local/db/init-local-db.sh

db-up:
	@$(COMPOSE) up -d

db-down:
	@$(COMPOSE) down

dba:
	@cd $(ONBOARDED_DIR) && OB_REPO_ROOT=$(ONBOARDED_DIR) PYTHONPATH=packages/dba/src $(DBA_PY) -m dba --tenant $(OB_TENANT) $(ARGS)

dba-test:
	@cd $(ONBOARDED_DIR)/packages/dba && $(DBA_PY) -m pytest -q

i:
	@$(PY) $(ONBOARDED_DIR)/packages/core/scripts/ob_instance.py $(ARGS)
