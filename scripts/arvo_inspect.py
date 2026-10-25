#!/usr/bin/env python3
"""Look inside ARVO images to find each project's runnable test suite (fills cases/arvo.TESTS).

Per id: pull -> print build.sh, the source tree's test layout and available tools -> optionally
rebuild with our flags and try a candidate test command -> docker rmi. Output:
runs/arvo_inspect/<id>.txt. Needs Docker (submit through workerq).
Usage: scripts/arvo_inspect.py --ids 42530604,42520955 [--try "id=make check"]
  [--net-prep "id=apt-get install -y libcunit1-dev"]  (network on for that try: inspection only,
  never the gate; a suite found this way is installed in the baseline prep, D-0071)
"""

from __future__ import annotations

import argparse
import subprocess
import sys

from leakproof.cases.arvo import BUILD_ENV, ArvoCase
from leakproof.config import RUNS_DIR
from leakproof.runner import ImageRef, LocalDockerRunner

INSPECT = r"""
P={project}
echo "## workdir: $(pwd)"; echo "## build.sh"; cat /src/build.sh
echo "## tree"; ls /src; ls /src/$P
echo "## test dirs"; find /src/$P -maxdepth 2 -iname '*test*' | head -40
echo "## make targets"; grep -hoE '^(check|test|tests|unittest)[a-zA-Z_-]*:' /src/$P/Makefile* /src/$P/*/Makefile* 2>/dev/null | sort -u
echo "## tools"; for t in make cmake python3 autoreconf ctest valgrind pkg-config; do printf '%s: ' $t; command -v $t || echo missing; done
echo "## cunit"; ls /usr/include/CUnit 2>/dev/null | head -3 || echo none
echo "## /bin/arvo"; cat /bin/arvo
echo "## engine env"; env | grep -E '^(FUZZING_ENGINE|SANITIZER|CC|CXX|LIB_FUZZING_ENGINE|ARCHITECTURE|FUZZING_LANGUAGE)=' | sort
echo "## compile"; command -v compile; head -60 "$(command -v compile)" 2>/dev/null
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", required=True)
    ap.add_argument(
        "--try",
        dest="try_cmd",
        action="append",
        default=[],
        help="id=command to run after an -O0 rebuild (repeatable)",
    )
    ap.add_argument("--net-prep", action="append", default=[], help="id=command, network on")
    args = ap.parse_args()
    preps = dict(t.split("=", 1) for t in args.net_prep)
    tries = dict(t.split("=", 1) for t in args.try_cmd)
    out_dir = RUNS_DIR / "arvo_inspect"
    out_dir.mkdir(parents=True, exist_ok=True)
    runner = LocalDockerRunner(memory="4g", cpus=2)
    for cid in args.ids.split(","):
        case = ArvoCase.load(cid)
        subprocess.run(["docker", "pull", "-q", case.image], check=True, capture_output=True)
        workdir = (
            subprocess.run(
                ["docker", "image", "inspect", "-f", "{{.Config.WorkingDir}}", case.image],
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
            or "/src"
        )
        ref = ImageRef("docker", case.image)
        res = runner.run(
            ref, INSPECT.format(project=case.project), cwd=workdir, network=False, timeout_s=120
        )
        text = f"# {cid} {case.project} {case.image} workdir={workdir}\n{res.stdout}\n{res.stderr[-2000:]}"
        if cid in tries:
            t = runner.run(
                ref,
                (
                    f"( {preps[cid]} ) > /tmp/prep.log 2>&1; echo PREP_RC=$?; tail -5 /tmp/prep.log; "
                    if cid in preps
                    else ""
                )
                + f"arvo compile > /tmp/c.log 2>&1 || {{ tail -30 /tmp/c.log; exit 97; }}; "
                f"arvo; echo ARVO_RC=$?; ( {tries[cid]} ) 2>&1 | tail -80; echo TEST_RC=$?",
                env=BUILD_ENV,
                cwd=workdir,
                network=cid in preps,
                timeout_s=2400,
            )
            text += f"\n## try: {tries[cid]} (exit {t.exit_code}, {t.elapsed_s}s)\n{t.stdout[-12000:]}\n{t.stderr[-3000:]}"
        (out_dir / f"{cid}.txt").write_text(text)
        print(text[:3000], flush=True)
        runner.remove_image(ref)
    return 0


if __name__ == "__main__":
    sys.exit(main())
