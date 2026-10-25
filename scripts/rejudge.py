#!/usr/bin/env python3
"""Re-gate saved candidates under the current gate: no model calls, $0.

For each case: prepare the baseline once, then for every source run gate that run's
runs/<run>/<case>/candidates.json again, and record old (gate.json) vs new verdict per candidate.
Output: runs/<out>/<case>/<run>/{gate.json, gate_artifacts/}, runs/<out>/summary.json.

Needs Docker: submit through workerq, e.g.
  workerq submit --project nebius-hackathon --ram 8 --cpus 4 -- powershell -NoProfile \
    -ExecutionPolicy Bypass -File scripts/lp_job.ps1 scripts/rejudge.py \
    --cases 42530604 --runs e1_arvo2_v4,e1_arvo2_v2 --out p0_rejudge_jq
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
import time
from pathlib import Path

from leakproof.cases import load_case
from leakproof.config import RUNS_DIR
from leakproof.fix import run_gate_process
from leakproof.runner import LocalDockerRunner


def progress(frac: float) -> None:
    path = os.environ.get("WORKERQ_PROGRESS")
    if path:
        with contextlib.suppress(OSError):
            Path(path).write_text(f"{frac:.3f}")


def rejudge_case(
    case_id: str, runs: list[str], out: Path, runner: LocalDockerRunner, developer: bool = False
) -> dict:
    rec: dict = {"case": case_id, "runs": {}}
    case = load_case(case_id)
    t0 = time.monotonic()
    ref = None
    try:
        baseline = case.prepare(runner)
        rec["prepare_s"] = round(time.monotonic() - t0, 1)
        if developer:
            # The same reference the ARVO runs were gated with (D-0052): refuzz attribution
            # does not blame a candidate for a crash the developer's fix also has.
            from leakproof.calibrate import build_reference, dev_fix_candidate

            dev, meta = dev_fix_candidate(case, runner, baseline)
            if dev is not None:
                ref, err = build_reference(case, runner, baseline, dev["files"])
                rec["reference"] = ref.ref if ref else f"build failed: {err[-300:]}"
            else:
                rec["reference"] = f"none: {meta.get('error')}"
        rec["finding_location"] = case.finding.get("location")
        for run in runs:
            src = RUNS_DIR / run / case_id
            if not (src / "candidates.json").exists():
                rec["runs"][run] = {"error": "no candidates.json"}
                continue
            payload = json.loads((src / "candidates.json").read_text())
            old = (
                json.loads((src / "gate.json").read_text()) if (src / "gate.json").exists() else {}
            )
            case_dir = out / case_id / run
            case_dir.mkdir(parents=True, exist_ok=True)
            new = run_gate_process(
                case_id,
                baseline.ref,
                getattr(case, "workdir", None),
                case.finding or payload.get("finding", {}),
                payload["candidates"],
                case_dir,
                reference=ref.ref if ref else None,
            )
            olds = {(r["hypothesis_id"], r["worker_index"]): r for r in old.get("results", [])}
            rows = []
            for r in new["results"]:
                o = olds.get((r["hypothesis_id"], r["worker_index"]), {})
                rows.append(
                    {
                        "hypothesis_id": r["hypothesis_id"],
                        "worker_index": r["worker_index"],
                        "v0": o.get("verdict"),
                        "v1": r["verdict"],
                        "refuzz": r["checks"].get("refuzz", {}).get("detail"),
                        "differential": r["checks"].get("differential", {}).get("detail"),
                        "safe_fix": r["checks"].get("safe_fix", {}).get("detail"),
                        "artifacts": r.get("artifacts", []),
                        "elapsed_s": r["elapsed_s"],
                    }
                )
            rec["runs"][run] = {
                "old_gate_version": old.get("gate_version", "v0"),
                "corpus": new.get("corpus"),
                "candidates": rows,
            }
    except Exception as exc:  # noqa: BLE001 - record and continue with the next case
        rec["error"] = f"{type(exc).__name__}: {exc}"[:2000]
    finally:
        if ref is not None:
            runner.remove_image(ref)
        if hasattr(case, "cleanup"):
            case.cleanup(runner)
    rec["elapsed_s"] = round(time.monotonic() - t0, 1)
    return rec


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", required=True, help="comma-separated case ids")
    ap.add_argument("--runs", required=True, help="comma-separated source run dirs under runs/")
    ap.add_argument("--out", required=True)
    ap.add_argument(
        "--reference",
        choices=["none", "developer"],
        default="none",
        help="developer: gate with the developer's fix as refuzz reference, like the ARVO runs",
    )
    args = ap.parse_args()
    out = RUNS_DIR / args.out
    out.mkdir(parents=True, exist_ok=True)
    runner = LocalDockerRunner(memory="4g", cpus=2)
    cases = [c for c in args.cases.split(",") if c]
    runs = [r for r in args.runs.split(",") if r]
    recs = []
    for i, cid in enumerate(cases):
        recs.append(rejudge_case(cid, runs, out, runner, args.reference == "developer"))
        (out / "summary.json").write_text(json.dumps({"cases": recs}, indent=1))
        progress((i + 1) / len(cases))
    for rec in recs:
        print(rec["case"], rec.get("error", ""))
        for run, r in rec["runs"].items():
            for c in r.get("candidates", []):
                print(f"  {run} {c['hypothesis_id']} w{c['worker_index']}: {c['v0']} -> {c['v1']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
