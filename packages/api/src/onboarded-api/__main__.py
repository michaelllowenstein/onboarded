"""
``python -m onboarded_api`` / ``onboarded-api`` — serve the API with uvicorn.

    python -m onboarded_api [--host H] [--port P] [--reload]

Defaults come from OB_API_HOST / OB_API_PORT (127.0.0.1:8000); flags override them.
``--help`` works without uvicorn installed.
"""

from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    from onboarded_api import __version__
    from onboarded_api.settings import Settings

    p = argparse.ArgumentParser(prog="onboarded-api", description="Serve the Onboarded REST API.")
    p.add_argument("--host", help="bind address (default: $OB_API_HOST or 127.0.0.1)")
    p.add_argument("--port", type=int, help="port (default: $OB_API_PORT or 8000)")
    p.add_argument("--reload", action="store_true", help="restart on code changes (development)")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    a = p.parse_args(argv)

    try:
        import uvicorn
    except ImportError:
        print("uvicorn is not installed: pip install -e 'packages/api[test]'  (or: just mvp-install)",
              file=sys.stderr)
        return 2

    s = Settings.from_env()
    uvicorn.run("onboarded_api.main:create_app", factory=True,
                host=a.host or s.host, port=a.port or s.port, reload=a.reload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
