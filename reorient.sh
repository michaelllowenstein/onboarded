#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# reorient.sh — point your system at THIS checkout after anything moves.
#
#   ./reorient.sh                       check: list every stale path (read-only)
#   ./reorient.sh --apply               fix everything check reports (backs up first)
#   ./reorient.sh --workspace ~/ws --msi-nav ~/code/msi-nav --apply
#   ./reorient.sh where | env | backups | restore <id> --apply | move-workspace <new> --apply
#
# Runs from wherever the repo now lives; nothing in it is hard-coded.
# Full help: python3 packages/core/scripts/ob_paths.py --help
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
PY="$(command -v python3 || true)"
[[ -n "$PY" ]] || { echo "reorient: python3 is required" >&2; exit 2; }
TOOL="$HERE/packages/core/scripts/ob_paths.py"
case "${1:-}" in
    "")                exec "$PY" "$TOOL" check ;;
    -*)                exec "$PY" "$TOOL" fix "$@" ;;          # ./reorient.sh --apply [--workspace …]
    *)                 exec "$PY" "$TOOL" "$@" ;;
esac
