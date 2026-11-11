"""Allows `python3 -m sysopt <command>`."""
import sys

from .cli import main

sys.exit(main())
