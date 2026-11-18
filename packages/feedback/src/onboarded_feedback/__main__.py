"""``python -m onboarded_feedback`` — identical to the ``ob-feedback`` console script."""

import sys

from onboarded_feedback.cli.main import main

if __name__ == "__main__":
    sys.exit(main())
