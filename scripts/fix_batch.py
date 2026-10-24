#!/usr/bin/env python3
"""Run the fix loop over a set of cases and write runs/<run_id>/{<case>.json, summary.json}.

Needs Docker: submit through workerq (D-0027), e.g.
  workerq submit --project nebius-hackathon --ram 8 --cpus 6 -- powershell -NoProfile \
    -ExecutionPolicy Bypass -File scripts/lp_job.ps1 scripts/fix_batch.py --cases juliet-smoke

--cases: juliet-smoke | comma-separated ids (CWE… = Juliet, digits = ARVO)
--planner: ultra | super | none (leaderboard baseline: workers without a plan)
Budget: --budget is this batch's Token Factory cap; LEAKPROOF_LEDGER_CAP_USD (default 25) caps
the whole ledger file.
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import contextlib
import json
import os
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

from leakproof.config import RUNS_DIR, load_dotenv
from leakproof.fix import fix_case
from leakproof.llm import CostLedger, LLMClient
from leakproof.runner import LocalDockerRunner, get_runner

ROOT = Path(__file__).resolve().parent.parent


def case_ids(spec: str) -> list[str]:
    if spec == "juliet-smoke":
        sel = json.loads((ROOT / "cases" / "juliet" / "selection.json").read_text())["cases"]
        return [c["id"] for c in sel]
    if spec.startswith("selection:"):  # any Juliet selection file, e.g. selection_cwe401_100
        path = ROOT / "cases" / "juliet" / f"{spec.split(':', 1)[1]}.json"
        return [c["id"] for c in json.loads(path.read_text())["cases"]]
    if spec == "batch_p3":
        sel = json.loads((ROOT / "cases" / "arvo" / "batch_p3.json").read_text())["cases"]
        return [str(c["localId"]) for c in sel]
    return [s.strip() for s in spec.split(",") if s.strip()]


def developer_reference(case, runner, baseline):  # noqa: ANN001, ANN201 - fix_case callback
    """Gate side (this script, not the worker path): the developer's fix built on the baseline,
    called by fix_case after the workers are done (D-0052)."""
    from leakproof.calibrate import build_reference, dev_fix_candidate

    if getattr(case, "suite", "") != "arvo":
        return None, None
    dev, meta = dev_fix_candidate(case, runner, baseline)
    if dev is None:
        return None, {"error": meta.get("error")}
    ref, err = build_reference(case, runner, baseline, dev["files"])
    info = {"commits": meta.get("commits"), "files": meta.get("files"), "partial": meta["partial"]}
    return (ref.ref if ref else None), info | ({"build_error": err[-300:]} if err else {})


def v0_verdict(worker: dict) -> str | None:
    """The verdict without v1's checks 5-7: the funnel's middle column (raw -> v0 -> v1)."""
    from leakproof.gate import Check, decide

    checks = (worker.get("gate") or {}).get("checks")
    if not checks:
        return None
    return decide(
        {
            k: Check(v["status"], v["detail"])
            for k, v in checks.items()
            if k not in ("differential", "refuzz", "safe_fix")
        }
    )


def progress(frac: float) -> None:
    path = os.environ.get("WORKERQ_PROGRESS")
    if path:
        with contextlib.suppress(OSError):
            Path(path).write_text(f"{frac:.3f}")


def summarize(recs: list[dict], args: argparse.Namespace, wall: float) -> dict:
    verdicts = Counter(r["verdict"].split(":", 1)[0] for r in recs)
    by_cwe: dict[str, Counter] = defaultdict(Counter)
    for r in recs:
        f = r.get("finding") or {}
        key = f.get("cwe_guess") or "unknown"
        by_cwe[key]["cases"] += 1
        by_cwe[key][r["verdict"].split(":", 1)[0]] += 1
    usd = sum(r.get("usd", 0.0) for r in recs)
    verified = verdicts.get("verified", 0)
    raw = sum(
        1
        for r in recs
        if any(
            (w.get("gate") or {}).get("checks", {}).get("patched", {}).get("status") == "pass"
            for w in r.get("workers", [])
        )
    )
    v0 = sum(1 for r in recs if any(v0_verdict(w) == "verified" for w in r.get("workers", [])))
    lat = sorted(r["elapsed_s"] for r in recs)
    return {
        "run_id": args.run_id,
        "planner": args.planner,
        "workers": args.workers,
        "cases": len(recs),
        "verdicts": dict(verdicts),
        "verified": verified,
        "verified_rate": round(verified / max(len(recs), 1), 3),
        "raw_crash_gone": raw,
        "raw_crash_gone_rate": round(raw / max(len(recs), 1), 3),
        "v0_verified": v0,
        # Round 1 vs after the repair round, never merged silently (B2).
        "verified_round1": sum(r.get("verdict_round1", r["verdict"]) == "verified" for r in recs),
        "verified_in_round2": sum(r.get("verified_in_round") == 2 for r in recs),
        "v0_verified_rate": round(v0 / max(len(recs), 1), 3),
        "per_cwe": {k: dict(v) for k, v in sorted(by_cwe.items())},
        "usd_total": round(usd, 4),
        "usd_per_verified": round(usd / verified, 4) if verified else None,
        "p50_case_s": lat[len(lat) // 2] if lat else None,
        "wall_s": round(wall, 1),
        "gate_version": "v0",
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", required=True)
    ap.add_argument("--run-id", default=None)
    ap.add_argument("--planner", default="ultra", choices=["ultra", "super", "none"])
    ap.add_argument("--worker-model", default="lightning")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--jobs", type=int, default=3, help="cases in parallel (ARVO: forced to 1)")
    ap.add_argument("--budget", type=float, default=3.0)
    ap.add_argument("--case-budget", type=float, default=0.5)
    ap.add_argument("--limit", type=int)
    ap.add_argument(
        "--reference",
        choices=["none", "developer"],
        default="none",
        help="ARVO: build the developer fix as the gate's attribution reference (P3)",
    )
    ap.add_argument("--audit-model", default="lightning", help="'none' disables check 8")
    ap.add_argument("--runner", default="docker", choices=["docker", "sandboxes"])
    ap.add_argument("--repair-rounds", type=int, default=0, help="B2: one repair round = 1")
    args = ap.parse_args()
    load_dotenv()
    os.environ.setdefault("LEAKPROOF_LEDGER_CAP_USD", "25")
    ids = case_ids(args.cases)[: args.limit]
    args.run_id = args.run_id or f"fix_{time.strftime('%Y%m%d_%H%M%S')}"
    run_dir = RUNS_DIR / args.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    runner = (
        LocalDockerRunner(memory="4g", cpus=2)
        if args.runner == "docker"
        else get_runner(args.runner, run_id=args.run_id)
    )
    # ARVO on Docker: one case at a time (D-0027). Sandboxes runs remotely: parallel is fine.
    jobs = 1 if args.runner == "docker" and any(i.isdigit() for i in ids) else args.jobs
    t0, recs, spent = time.monotonic(), [], 0.0

    def one(cid: str) -> dict:
        client = LLMClient(
            ledger=CostLedger(budget=args.case_budget), run_id=f"{args.run_id}:{cid}"
        )
        # Sandboxes: a runner per case, so each record carries only its own lineage.
        case_runner = (
            runner
            if args.runner == "docker"
            else get_runner(args.runner, run_id=f"{args.run_id}:{cid}")
        )
        return fix_case(
            cid,
            run_dir,
            client,
            case_runner,
            planner_model=None if args.planner == "none" else args.planner,
            worker_model=args.worker_model,
            n_workers=args.workers,
            audit_model=None if args.audit_model == "none" else args.audit_model,
            reference_builder=developer_reference if args.reference == "developer" else None,
            repair_rounds=args.repair_rounds,
        )

    # Resume: a case with a finished record (not an infrastructure error) is not re-run, so a
    # preempted batch continues where it stopped and its spend is still counted.
    for cid in ids:
        path = run_dir / f"{cid}.json"
        if path.exists():
            r = json.loads(path.read_text())
            if not r.get("verdict", "").startswith("error"):
                recs.append(r)
                spent += r.get("usd", 0.0)
    done_ids = {r["case"] for r in recs}
    with cf.ThreadPoolExecutor(jobs) as pool:
        pending = {}
        queue = [i for i in ids if i not in done_ids]
        while queue or pending:
            while queue and len(pending) < jobs and spent < args.budget:
                cid = queue.pop(0)
                pending[pool.submit(one, cid)] = cid
            if not pending:
                print(
                    f"batch budget ${args.budget} reached; {len(queue)} cases not run", flush=True
                )
                break
            done, _ = cf.wait(pending, return_when=cf.FIRST_COMPLETED)
            for fut in done:
                cid = pending.pop(fut)
                r = fut.result()
                recs.append(r)
                spent += r.get("usd", 0.0)
                print(
                    f"{r['verdict']:<40} {cid}  ${r.get('usd', 0):.4f}  {r['elapsed_s']}s",
                    flush=True,
                )
                progress(len(recs) / len(ids))
    summary = summarize(recs, args, time.monotonic() - t0)
    summary["not_run"] = [i for i in ids if i not in {r["case"] for r in recs}]
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
