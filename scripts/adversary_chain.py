#!/usr/bin/env python3
"""Run several adversary_eval.py sets one after another in one Docker job (one Docker job at a
time on this machine). scripts/adversary_chain.py ROOT SET[:ONLY] ..."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

root = sys.argv[1]
for spec in sys.argv[2:]:
    which, _, only = spec.partition(":")
    cmd = [sys.executable, str(Path(__file__).with_name("adversary_eval.py")), which, root]
    print("== chain:", spec, flush=True)
    subprocess.run(cmd + ([only] if only else []), check=False)
