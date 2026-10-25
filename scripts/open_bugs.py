#!/usr/bin/env python3
"""Open, public bugs at upstream HEAD (review #6 order 1): does each reproducer still trip?

scripts/open_bugs.py reproduce   -> runs/open_bugs/reproduce.json (no model calls)
scripts/open_bugs.py fix         -> `leakproof fix` on every case that reproduced, one at a time,
                                    each with its own --budget (runs/open_bugs_fix/)

Cases are cases/open_bugs/**/leakproof.toml; upstream clones live next to them (not committed),
so a workerq job, which runs from a git snapshot without them, passes the live checkout's
directory with --cases-dir. Needs Docker: submit through workerq (scripts/lp_job.ps1).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

from leakproof.cases.project import ProjectCase
from leakproof.config import REPO_ROOT, RUNS_DIR
from leakproof.runner import LocalDockerRunner

CASES = REPO_ROOT / "cases" / "open_bugs"
OUT = RUNS_DIR / "open_bugs"


def configs(cases: Path) -> list[Path]:
    return sorted(
        p for p in cases.rglob("leakproof.toml") if "src" not in p.relative_to(cases).parts
    )


def reproduce(cases: Path) -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    runner = LocalDockerRunner(memory="4g", cpus=2)
    rows = []
    for toml in configs(cases):
        case = ProjectCase.load(f"project:{toml}")
        t0 = time.monotonic()
        row = {"case": case.project, "config": toml.relative_to(cases).as_posix()}
        try:
            case.prepare(runner)
            row |= {
                "reproduces": True,
                "finding": {k: case.finding.get(k) for k in ("kind", "location")},
            }
        except RuntimeError as exc:
            msg = str(exc)
            row |= {
                "reproduces": False,
                "why": "build failed" if "build failed" in msg else "did not trip at HEAD",
                "detail": msg[-1200:],
            }
        finally:
            case.cleanup(runner)
        row["s"] = round(time.monotonic() - t0, 1)
        rows.append(row)
        print(json.dumps(row)[:400], flush=True)
        (OUT / "reproduce.json").write_text(json.dumps(rows, indent=1))
    return 0


def fix(cases: Path, budget: float, only: set[str] | None) -> int:
    rows = json.loads((OUT / "reproduce.json").read_text())
    for row in rows:
        if not row.get("reproduces") or (only and row["case"] not in only):
            continue
        cmd = [
            sys.executable,
            "-m",
            "leakproof.cli",
            "fix",
            "--config",
            str(cases / row["config"]),
            "--run-id",
            "open_bugs_fix",
            "--budget",
            str(budget),
        ]
        print("$", " ".join(cmd[2:]), flush=True)
        subprocess.run(cmd, check=False)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=["reproduce", "fix"])
    ap.add_argument("--budget", type=float, default=0.3, help="USD cap per case (fix)")
    ap.add_argument("--cases-dir", type=Path, default=CASES)
    ap.add_argument("--only", help="comma-separated case names (fix)")
    args = ap.parse_args()
    cases = args.cases_dir.resolve()
    if args.step == "reproduce":
        return reproduce(cases)
    return fix(cases, args.budget, set(args.only.split(",")) if args.only else None)


if __name__ == "__main__":
    sys.exit(main())
