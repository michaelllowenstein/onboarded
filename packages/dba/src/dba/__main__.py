"""``python -m dba`` — identical to the ``ob-dba`` console script (see :mod:`dba.cli`)."""

import sys

from dba.cli import main

if __name__ == "__main__":
    sys.exit(main())
