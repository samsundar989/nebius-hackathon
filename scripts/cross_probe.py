#!/usr/bin/env python3
"""Attribute a cross-candidate split (D-0070): the separating inputs on the baseline and on the
developer's fix. A split where the developer's fix crashes too is a second, pre-existing bug
that some candidates also fixed; one where only some candidates crash is a defect of theirs.

scripts/cross_probe.py --cases 42500232,42508524 -> adds "probe" to runs/cross_diff/<case>.json
Needs Docker: submit through workerq (scripts/lp_job.ps1). No model calls.
"""

from __future__ import annotations

import argparse
import base64
import json
import sys

from leakproof import gate_fuzz as gf
from leakproof.calibrate import build_reference, dev_fix_candidate
from leakproof.cases import load_case
from leakproof.config import RUNS_DIR
from leakproof.gate import ArvoGate
from leakproof.runner import LocalDockerRunner


def sig(report: str) -> str:
    key = gf.crash_key(report)
    return f"{key[0]} at {key[1] or '?'}" if key else "clean"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", required=True)
    args = ap.parse_args()
    runner = LocalDockerRunner(memory="4g", cpus=2)
    for cid in args.cases.split(","):
        path = RUNS_DIR / "cross_diff" / f"{cid}.json"
        rec = json.loads(path.read_text())
        inputs = {
            s["input"]: base64.b64decode(s["b64"]) for s in rec["separating_inputs"] if s["b64"]
        }
        case = load_case(cid)
        ref = None
        try:
            baseline = case.prepare(runner)
            gate = ArvoGate(case, runner, baseline)
            dev, meta = dev_fix_candidate(case, runner, baseline)
            if dev is not None:
                ref, err = build_reference(case, runner, baseline, dev["files"])
            rec["probe"] = {
                name: {
                    "baseline": sig(gate.probe(baseline, data)),
                    "developer_fix": sig(gate.probe(ref, data)) if ref else "not built",
                }
                for name, data in inputs.items()
            }
        except Exception as exc:  # noqa: BLE001 - record and continue
            rec["probe_error"] = f"{type(exc).__name__}: {exc}"[:1000]
        finally:
            if ref is not None:
                runner.remove_image(ref)
            case.cleanup(runner)
        path.write_text(json.dumps(rec, indent=1))
        print(cid, json.dumps(rec.get("probe") or rec.get("probe_error"), indent=1), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
