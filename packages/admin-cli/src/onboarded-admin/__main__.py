"""``python -m onboarded_admin`` — identical to the ``ob-admin`` console script."""

import sys

from onboarded_admin.cli import main

if __name__ == "__main__":
    sys.exit(main())
