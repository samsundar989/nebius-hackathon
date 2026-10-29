#!/usr/bin/env python3
"""Check a bring-your-own config before spending on it: build, reproduce, tests. No model calls.

scripts/probe_case.py --config cases/real_world/<repo>/<issue>/leakproof.toml [--keep]

Runs exactly what `leakproof fix` runs before planning (ProjectCase.prepare: the build, then the
reproducer, which must trip a sanitizer), then the project's tests on that baseline, and prints
the finding, the timings and the per-test counts the gate will compare against. Needs Docker:
submit through workerq (LEAKPROOF_DOCKER_CPUS / _MEMORY for a large project).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from leakproof.cases.project import ProjectCase
from leakproof.gate import MARK, TEST_LINES, test_results
from leakproof.runner import LocalDockerRunner


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", type=Path, required=True)
    ap.add_argument("--keep", action="store_true", help="keep the baseline image")
    args = ap.parse_args()
    case = ProjectCase.load(f"project:{args.config.resolve()}")
    runner = LocalDockerRunner()
    print(f"runner: {runner.cpus} CPUs, {runner.memory}")
    t0 = time.monotonic()
    try:
        image = case.prepare(runner)
    except RuntimeError as exc:
        print(f"PREPARE FAILED after {time.monotonic() - t0:.0f} s:\n{exc}")
        return 1
    print(f"prepare: {case.prep}")
    print("finding:", json.dumps(case.finding))
    print(case.prep.get("report_tail", "")[-2500:])
    if case.tests_cmd:
        t1 = time.monotonic()
        res = runner.run(
            image,
            f"( {case.tests_cmd} ) > /tmp/t.log 2>&1; rc=$?; grep -E {TEST_LINES} /tmp/t.log; "
            f"printf '\n{MARK} tail\n'; tail -25 /tmp/t.log; exit $rc",
            env=case.build_env,
            cwd=case.workdir,
            timeout_s=3600,
            network=False,
        )
        head, _, tail = res.stdout.partition(f"\n{MARK} tail\n")
        results = test_results(head)
        failing = sorted(n for n, ok in results.items() if not ok)
        print(
            f"tests: exit {res.exit_code} in {time.monotonic() - t1:.0f} s; parsed {len(results)}, "
            f"pass {len(results) - len(failing)}, fail {len(failing)} {failing[:10]}"
        )
        print(tail[-1500:])
    if not args.keep:
        case.cleanup(runner)
    return 0


if __name__ == "__main__":
    sys.exit(main())
