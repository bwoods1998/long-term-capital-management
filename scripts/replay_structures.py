#!/usr/bin/env python3
"""Replay private programs with the current sealed Gym. Output remains private.

Train and Validation only. Holdout belongs to the gate.
All options except the enforced window are those of `python -m league.gym.batch`.
"""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

def main(argv=None):
    from league.gym.batch import main as batch
    args = list(sys.argv[1:] if argv is None else argv)
    if "--help" in args or "-h" in args:
        return batch(args)
    import argparse
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--window", choices=('train', 'validation'), default='train')
    known, rest = p.parse_known_args(args)
    return batch(["--window", known.window, *rest])

if __name__ == "__main__":
    raise SystemExit(main())
