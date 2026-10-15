"""Run PowDroid from a source checkout: python powdroid.py (GUI) or python powdroid.py -o csv (CLI).

The powdroid/ package next to this file takes precedence over it when importing "powdroid".
"""

import sys

from powdroid.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
