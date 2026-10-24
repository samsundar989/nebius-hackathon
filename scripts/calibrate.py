#!/usr/bin/env python3
"""P1 calibration: does the gate accept the developers' own fixes? No model calls, $0.

Per ARVO case:
  1 prepare the -O0 baseline (as the fix loop does)
  2 apply the upstream fix commit to the baseline (leakproof.calibrate) and gate it with
    baseline-only attribution, i.e. exactly as a model candidate is judged -> `dev` verdict
  3 build the developer fix as a reference image; re-gate saved model candidates from --runs
    with it (refuzz crashes the developer fix also shows are not blamed)
  4 --probe: run saved crash inputs (runs/<dir>/<case>/<run>/gate_artifacts/*.bin) through the
    baseline and the reference
Writes runs/<out>/<case>/calibration.json (+ gate dirs); skips cases already done, so a
preempted job resumes where it stopped.

  workerq submit --project nebius-hackathon --ram 8 --cpus 4 --preemptible -- powershell \
    -NoProfile -ExecutionPolicy Bypass -File scripts/lp_job.ps1 scripts/calibrate.py \
    --cases tier1 --out p1_calibration
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
import time
from pathlib import Path

from leakproof import gate_fuzz as gf
from leakproof.calibrate import build_reference, dev_fix_candidate
from leakproof.cases.arvo import SHORTLIST, ArvoCase
from leakproof.config import RUNS_DIR
from leakproof.fix import run_gate_process
from leakproof.gate import ArvoGate
from leakproof.runner import ImageRef, LocalDockerRunner


def progress(frac: float) -> None:
    path = os.environ.get("WORKERQ_PROGRESS")
    if path:
        with contextlib.suppress(OSError):
            Path(path).write_text(f"{frac:.3f}")


def case_ids(spec: str) -> list[str]:
    if spec in ("tier1", "tier2", "reserves"):
        return [str(r["localId"]) for r in json.loads(SHORTLIST.read_text())[spec]]
    return [s.strip() for s in spec.split(",") if s.strip()]


def _short(result: dict) -> dict:
    return {
        "verdict": result["verdict"],
        "checks": {k: f"{v['status']}: {v['detail'][:300]}" for k, v in result["checks"].items()},
        "artifacts": result.get("artifacts", []),
        "elapsed_s": result["elapsed_s"],
    }


def calibrate_case(
    cid: str, runs: list[str], probe_dirs: list[str], out: Path, runner: LocalDockerRunner
) -> dict:
    t0 = time.monotonic()
    case = ArvoCase.load(cid)
    rec: dict = {"case": cid, "project": case.project, "crash_type": case.crash_type}
    ref: ImageRef | None = None
    try:
        baseline = case.prepare(runner)
        rec["prep"] = case.prep | {"finding_location": case.finding.get("location")}
        dev, meta = dev_fix_candidate(case, runner, baseline)
        rec["dev_fix"] = meta
        if dev is None:
            rec["dev"] = {"verdict": "no_candidate:" + meta.get("error", "?")}
            return rec
        meta["diff_lines"] = dev["diff"].count("\n")
        (out / cid / "dev").mkdir(parents=True, exist_ok=True)
        gate = run_gate_process(
            cid, baseline.ref, case.workdir, case.finding, [dev], out / cid / "dev"
        )
        rec["dev"] = _short(gate["results"][0]) | {"corpus": gate.get("corpus")}
        ref, err = build_reference(case, runner, baseline, dev["files"])
        rec["reference"] = ref.ref if ref else f"build failed: {err[-400:]}"
        for run in runs:
            src = RUNS_DIR / run / cid / "candidates.json"
            if not src.exists() or ref is None:
                continue
            payload = json.loads(src.read_text())
            (out / cid / run).mkdir(parents=True, exist_ok=True)
            g = run_gate_process(
                cid,
                baseline.ref,
                case.workdir,
                case.finding,
                payload["candidates"],
                out / cid / run,
                reference=ref.ref,
            )
            rec.setdefault("models", {})[run] = [
                {"hypothesis_id": r["hypothesis_id"], "worker_index": r["worker_index"]} | _short(r)
                for r in g["results"]
            ]
        probes = sorted(
            p for d in probe_dirs for p in (RUNS_DIR / d / cid).glob("*/gate_artifacts/*.bin")
        )
        if probes:
            ag = ArvoGate(case, runner, baseline)
            rec["probes"] = []
            for p in probes:
                data = p.read_bytes()
                b = gf.crash_key(ag.probe(baseline, data))
                r = gf.crash_key(ag.probe(ref, data)) if ref else None
                rec["probes"].append(
                    {"input": str(p.relative_to(RUNS_DIR)), "baseline": b, "developer_fix": r}
                )
    except Exception as exc:  # noqa: BLE001 - one case's failure is recorded, the batch goes on
        rec["error"] = f"{type(exc).__name__}: {exc}"[-2000:]
    finally:
        if ref is not None:
            runner.remove_image(ref)
        case.cleanup(runner)
        rec["elapsed_s"] = round(time.monotonic() - t0, 1)
    return rec


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", required=True, help="tier1 | tier2 | reserves | comma-separated ids")
    ap.add_argument("--runs", default="", help="model runs to re-gate with the reference")
    ap.add_argument("--probe", default="", help="run dirs whose saved crash inputs to probe")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    out = RUNS_DIR / args.out
    out.mkdir(parents=True, exist_ok=True)
    runner = LocalDockerRunner(memory="4g", cpus=2)
    ids = case_ids(args.cases)
    runs = [r for r in args.runs.split(",") if r]
    probes = [p for p in args.probe.split(",") if p]
    for i, cid in enumerate(ids):
        path = out / cid / "calibration.json"
        if path.exists():
            continue
        rec = calibrate_case(cid, runs, probes, out, runner)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(rec, indent=1))
        dev = rec.get("dev", {}).get("verdict", rec.get("error", "?"))
        print(f"{cid} {rec['project']}: developer fix -> {dev} ({rec['elapsed_s']} s)", flush=True)
        for run, rows in rec.get("models", {}).items():
            for r in rows:
                print(f"  {run} {r['hypothesis_id']} w{r['worker_index']}: {r['verdict']}")
        for p in rec.get("probes", []):
            print(f"  probe {p['input']}: baseline {p['baseline']} | dev fix {p['developer_fix']}")
        progress((i + 1) / len(ids))
    return 0


if __name__ == "__main__":
    sys.exit(main())
