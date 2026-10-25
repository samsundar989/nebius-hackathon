#!/usr/bin/env python3
"""What could the differential observe? Harness output statistics per ARVO case (D-0074).

For runs gated before the gate recorded them: prepare the baseline, run the gate's own corpus
step (`ArvoGate.unpatched`), and keep how many corpus inputs run clean and how many distinct
non-empty stdouts they produce. No model calls, no candidates.

scripts/harness_output.py [--cases a,b]   -> runs/harness_output/<case>.json (resumes)
Default: every case with a verified candidate in the ARVO runs. Needs Docker (workerq).
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
from pathlib import Path

from leakproof import gate_fuzz as gf
from leakproof.cases import load_case
from leakproof.config import RUNS_DIR
from leakproof.gate import ArvoGate
from leakproof.runner import LocalDockerRunner
from leakproof.semantic import verified_candidates

OUT = RUNS_DIR / "harness_output"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    runner = LocalDockerRunner(memory="4g", cpus=2)
    todo = args.cases.split(",") if args.cases else sorted(verified_candidates())
    for i, cid in enumerate(todo):
        out = OUT / f"{cid}.json"
        if out.exists() and "error" not in json.loads(out.read_text()):
            continue
        case = load_case(cid)
        rec: dict = {"case": cid}
        try:
            gate = ArvoGate(case, runner, case.prepare(runner))
            rec["unpatched"] = gate.unpatched().to_dict()
            rec["corpus_source"] = gate.corpus_source
            rec["corpus_inputs"] = len(gate.base_diff)
            rec |= gf.output_stats(gate.base_diff)
        except Exception as exc:  # noqa: BLE001 - record and continue
            rec["error"] = f"{type(exc).__name__}: {exc}"[:1000]
        finally:
            case.cleanup(runner)
        out.write_text(json.dumps(rec, indent=1))
        print(
            cid,
            {k: rec.get(k) for k in ("corpus_inputs", "clean_inputs", "stdout_distinct")},
            rec.get("error", ""),
            flush=True,
        )
        if p := os.environ.get("WORKERQ_PROGRESS"):
            with contextlib.suppress(OSError):
                Path(p).write_text(f"{(i + 1) / len(todo):.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
