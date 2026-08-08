"""`python -m harness …`, identical to the `harness` console script.

Two ways in and no third. The console script is what you get after installing;
this is what works when PATH does not cooperate — a fresh install on macOS
often leaves `~/.local/bin` off it, and "command not found" is a bad first
impression of a tool that is, in fact, installed and working.
"""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
