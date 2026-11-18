# onboarded-feedback

Closes the loop between how people use the Onboarded CLI and what the tenant's
`domain.json` knows: local telemetry → gap detection → suggested domain edits.

| Module | Status |
|---|---|
| `telemetry.store` | **implemented** — SQLite at `~/.onboarded/<tenant>/telemetry.db`; keys and command names only |
| `cli.main` (`ob-feedback`) | `telemetry show / misses / scans` implemented; `suggest`, `doctor` exit 3 (not yet) |
| `domain_loader` | placeholder — the test suite specifies it |
| `gap_detection.*` | placeholder — specified by `tests/test_gap_detection.py` |
| `suggestion_engine.*` | placeholder — specified by `tests/test_suggestion_engine.py` |

The test suite cannot run until `domain_loader` exists (`tests/conftest.py` imports it).
Implementing the placeholders is roadmap §6 item 6.

```bash
pip install -e packages/feedback
ob-feedback telemetry show --tenant msi          # or: python -m onboarded_feedback telemetry show --tenant msi
```

The zsh hooks in `shell/` record events and call `ob-feedback` (falling back to
`python3 -m onboarded_feedback.cli.main`).
