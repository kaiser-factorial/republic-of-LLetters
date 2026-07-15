#!/usr/bin/env python3
"""Shim → twitter/tweet.py (kept for older docs / muscle memory)."""
from pathlib import Path
import runpy
import sys

sys.argv[0] = str(Path(__file__).resolve().parent / "twitter" / "tweet.py")
runpy.run_path(sys.argv[0], run_name="__main__")
