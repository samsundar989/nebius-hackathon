#!/usr/bin/env python3
"""P4 model leaderboard: planner configurations on a fixed Juliet subset, repeated.

  scripts/leaderboard.py run   [--repeats 3] [--runner sandboxes]   -> runs/lb_<config>_r<k>/
  scripts/leaderboard.py report                                      -> runs/leaderboard.json

Subset: cases/juliet/selection_leaderboard20.json (10 x CWE-401, 5 x 415, 5 x 416 from the
smoke set, seed 7; written on first use). Configurations (workers are always 4 x Lightning):
  lightning   no planner (workers get one hypothesis per frame)
  ultra       Nemotron-3 Ultra plans
  super       Nemotron-3 Super plans
Per configuration: verified rate mean +- spread over repeats, $/verified fix, p50 latency.
Each run is its own fix_batch call with its own budget (< $2, CLAUDE.md rule 4).
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import subprocess
import sys
from pathlib import Path

from leakproof.config import RUNS_DIR

ROOT = Path(__file__).resolve().parent.parent
SUBSET = ROOT / "cases" / "juliet" / "selection_leaderboard20.json"
CONFIGS = {"lightning": "none", "ultra": "ultra", "super": "super"}
QUOTA = {"401": 10, "415": 5, "416": 5}


ARVO_SUBSET = ROOT / "cases" / "arvo" / "selection_leaderboard10.json"


def subset(suite: str = "juliet") -> list[str]:
    if suite == "arvo":
        if not ARVO_SUBSET.exists():
            pool = sorted(
                str(c["localId"])
                for c in json.loads((ROOT / "cases" / "arvo" / "batch_p3.json").read_text())[
                    "cases"
                ]
            )
            picked = sorted(random.Random(7).sample(pool, 10))
            ARVO_SUBSET.write_text(json.dumps({"seed": 7, "cases": picked}, indent=1) + "\n")
        return json.loads(ARVO_SUBSET.read_text())["cases"]
    if not SUBSET.exists():
        smoke = json.loads((ROOT / "cases" / "juliet" / "selection.json").read_text())["cases"]
        rng = random.Random(7)
        picked = []
        for cwe, k in QUOTA.items():
            pool = sorted(c["id"] for c in smoke if c["id"].startswith(f"CWE{cwe}_"))
            picked += rng.sample(pool, k)
        SUBSET.write_text(json.dumps({"seed": 7, "cases": [{"id": i} for i in picked]}, indent=1))
    return [c["id"] for c in json.loads(SUBSET.read_text())["cases"]]


def run(args: argparse.Namespace) -> int:
    ids = subset(args.suite)
    prefix = "lb_arvo" if args.suite == "arvo" else "lb"
    for k in range(1, args.repeats + 1):
        for name, planner in CONFIGS.items():
            run_id = f"{prefix}_{name}_r{k}"
            if (RUNS_DIR / run_id / "summary.json").exists():
                continue
            cmd = [
                sys.executable,
                str(ROOT / "scripts" / "fix_batch.py"),
                "--cases",
                ",".join(ids) if args.suite == "arvo" else "selection:selection_leaderboard20",
                "--planner",
                planner,
                "--runner",
                args.runner,
                "--jobs",
                str(args.jobs),
                "--run-id",
                run_id,
                "--budget",
                "0.9",
                "--case-budget",
                "0.3" if args.suite == "arvo" else "0.1",
            ]
            if args.suite == "arvo":
                cmd += ["--reference", "developer"]
            print(f"== {run_id}", flush=True)
            subprocess.run(cmd, check=False, stdout=subprocess.DEVNULL)
    return report(args)


def report(args: argparse.Namespace) -> int:
    ids = subset(args.suite)
    prefix = "lb_arvo" if args.suite == "arvo" else "lb"
    rows = {}
    for name in CONFIGS:
        reps = []
        for path in sorted(RUNS_DIR.glob(f"{prefix}_{name}_r*/summary.json")):
            s = json.loads(path.read_text())
            recs = [json.loads((path.parent / f"{i}.json").read_text()) for i in ids]
            verified = sum(r["verdict"] == "verified" for r in recs)
            usd = sum(r.get("usd", 0.0) for r in recs)
            reps.append(
                {
                    "run": path.parent.name,
                    "verified": verified,
                    "rate": verified / len(ids),
                    "usd": round(usd, 4),
                    "p50_s": statistics.median(r["elapsed_s"] for r in recs),
                    "raw": s.get("raw_crash_gone"),
                }
            )
        if not reps:
            continue
        rates = [r["rate"] for r in reps]
        total_v = sum(r["verified"] for r in reps)
        rows[name] = {
            "repeats": len(reps),
            "verified_rate_mean": round(statistics.mean(rates), 3),
            "verified_rate_min": round(min(rates), 3),
            "verified_rate_max": round(max(rates), 3),
            "usd_per_verified": round(sum(r["usd"] for r in reps) / total_v, 4)
            if total_v
            else None,
            "p50_latency_s": round(statistics.median(r["p50_s"] for r in reps), 1),
            "runs": reps,
        }
    sub = ARVO_SUBSET if args.suite == "arvo" else SUBSET
    out = {
        "suite": args.suite,
        "cases": len(ids),
        "subset": str(sub.relative_to(ROOT)),
        "configs": rows,
    }
    name = "leaderboard_arvo.json" if args.suite == "arvo" else "leaderboard.json"
    (RUNS_DIR / name).write_text(json.dumps(out, indent=1))
    print("| config | repeats | verified (mean, min-max) | $/verified | p50 latency |")
    print("|---|---|---|---|---|")
    for name, r in rows.items():
        print(
            f"| {name} | {r['repeats']} | {r['verified_rate_mean']:.0%} "
            f"({r['verified_rate_min']:.0%}-{r['verified_rate_max']:.0%}) | "
            f"${r['usd_per_verified']} | {r['p50_latency_s']} s |"
        )
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["run", "report"])
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--runner", default="sandboxes")
    ap.add_argument("--jobs", type=int, default=8)
    ap.add_argument("--suite", choices=["juliet", "arvo"], default="juliet")
    args = ap.parse_args()
    return run(args) if args.action == "run" else report(args)


if __name__ == "__main__":
    sys.exit(main())
