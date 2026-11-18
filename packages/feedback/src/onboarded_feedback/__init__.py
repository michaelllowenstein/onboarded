"""
onboarded_feedback — telemetry, gap detection and domain suggestions for Onboarded.

Subpackages:
    telemetry          local SQLite event store (implemented)
    cli                ``ob-feedback`` command line (telemetry commands implemented)
    gap_detection      missing operations / stale paths       (placeholder)
    suggestion_engine  domain.json edit suggestions            (placeholder)

Run as ``ob-feedback`` (installed) or ``python -m onboarded_feedback``.
"""

__version__ = "0.1.0"

__all__ = ["__version__"]
