#!/usr/bin/env python3
"""Exercise the options program contract with synthetic quotes; no market evidence or order."""
from pathlib import Path
import json
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from league.canary import verify_runtime
if __name__ == "__main__":
    print(json.dumps(verify_runtime(), indent=2))
