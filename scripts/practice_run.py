#!/usr/bin/env python3
"""Finite local recorded/synthetic practice; never starts the House or a live feed."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from league.practice_runner import main

if __name__ == "__main__":
    raise SystemExit(main())
