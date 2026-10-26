#!/usr/bin/env python3
"""Run several adversary_eval.py sets one after another in one Docker job (one Docker job at a
time on this machine). scripts/adversary_chain.py ROOT [KEY=VALUE ...] SET[:ONLY] ..."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

root = sys.argv[1]
for spec in sys.argv[2:]:
    if "=" in spec and ":" not in spec.split("=", 1)[0]:
        # KEY=VALUE: an environment setting for the sets that follow (models, budget, tag).
        key, _, value = spec.partition("=")
        os.environ[key] = value
        continue
    which, _, only = spec.partition(":")
    cmd = [sys.executable, str(Path(__file__).with_name("adversary_eval.py")), which, root]
    print("== chain:", spec, flush=True)
    subprocess.run(cmd + ([only] if only else []), check=False)
