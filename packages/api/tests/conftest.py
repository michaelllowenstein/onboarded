"""
Fixtures. `settings` points at the real repo (so the suite doubles as a check
that every committed domain.json loads) and at a temp scan root seeded with
the CLI's scan fixtures.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from onboarded_api.services.domain_store import DomainStore
from onboarded_api.settings import Settings, find_repo_root

REPO = find_repo_root(Path(__file__))
FIXTURES = REPO / "packages" / "cli" / "tests" / "fixtures" / "scan_fixtures"


@pytest.fixture
def scan_root(tmp_path: Path) -> Path:
    root = tmp_path / "workspace"
    (root / "app").mkdir(parents=True)
    (root / "app" / "tests").mkdir()
    for f in FIXTURES.iterdir():
        shutil.copy2(f, root / "app" / f.name)
    shutil.copy2(FIXTURES / "ViolationService.cs", root / "app" / "tests" / "ViolationService.cs")
    return root


@pytest.fixture
def settings(scan_root: Path, tmp_path: Path) -> Settings:
    return Settings(repo_root=REPO, scan_roots=(scan_root,), home=tmp_path / "home")


@pytest.fixture
def store(settings: Settings) -> DomainStore:
    return DomainStore(settings.tenants_dir, settings.core_scripts).load()
