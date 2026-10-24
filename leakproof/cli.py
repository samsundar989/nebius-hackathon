"""`leakproof fix --config leakproof.toml`: the fix loop on your own C/C++ project (P5).

Same pipeline and evidence as the ARVO/Juliet runs: baseline build + reproduction, a Nemotron
plan, parallel workers on branches of one checkpoint, the gate in its own process with the
network off, the audit flag; writes runs/<run-id>/<case>.json and prints the funnel.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from leakproof.config import RUNS_DIR, load_dotenv
from leakproof.fix import case_slug, fix_case
from leakproof.llm import CostLedger, LLMClient
from leakproof.runner import LocalDockerRunner, get_runner


def _fix(args: argparse.Namespace) -> int:
    load_dotenv()
    config = Path(args.config).resolve()
    if not config.exists():
        print(f"no such config: {config}", file=sys.stderr)
        return 2
    run_id = args.run_id or f"project_{time.strftime('%Y%m%d_%H%M%S')}"
    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    runner = (
        LocalDockerRunner(memory="4g", cpus=2)
        if args.runner == "docker"
        else get_runner(args.runner, run_id=run_id)
    )
    client = LLMClient(ledger=CostLedger(budget=args.budget), run_id=f"{run_id}:project")
    rec = fix_case(
        f"project:{config}",
        run_dir,
        client,
        runner,
        planner_model=None if args.planner == "none" else args.planner,
        n_workers=args.workers,
    )
    workers = rec.get("workers", [])
    print(f"\nverdict: {rec['verdict']}   ${rec.get('usd', 0):.4f}   {rec.get('elapsed_s')} s")
    if rec.get("error"):
        print(rec["error"][:1500])
    for w in workers:
        flags = ",".join((w.get("audit") or {}).get("flags", [])) or "-"
        print(f"  {w['hypothesis_id']} w{w['worker_index']}: {w['verdict']:<36} audit: {flags}")
    if rec.get("winner"):
        print("\nwinning diff:\n" + rec["winner"]["diff"])
    print(f"\nrecord: {run_dir / (case_slug(rec['case']) + '.json')}")
    if args.json:
        print(json.dumps(rec, indent=1))
    return 0 if rec["verdict"] == "verified" else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="leakproof")
    sub = ap.add_subparsers(dest="cmd", required=True)
    fx = sub.add_parser("fix", help="fix the memory defect your `reproduce` command trips")
    fx.add_argument("--config", default="leakproof.toml")
    fx.add_argument("--runner", default="docker", choices=["docker", "sandboxes"])
    fx.add_argument("--planner", default="ultra", choices=["ultra", "super", "none"])
    fx.add_argument("--workers", type=int, default=4)
    fx.add_argument("--budget", type=float, default=0.5, help="USD cap for this run")
    fx.add_argument("--run-id")
    fx.add_argument("--json", action="store_true", help="also print the full record")
    args = ap.parse_args(argv)
    return _fix(args)


if __name__ == "__main__":
    sys.exit(main())
