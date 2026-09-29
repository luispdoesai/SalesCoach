#!/usr/bin/env python3
"""AI Sales Coach. Run `python coach.py --help` to see every command."""

import sys

if sys.version_info < (3, 10):
    sys.stderr.write(
        "\nProblem: AI Sales Coach needs Python 3.10 or newer. You have %d.%d.\n"
        "Fix: install a newer Python from https://www.python.org/downloads/\n" % sys.version_info[:2]
    )
    sys.exit(1)

from coach.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
