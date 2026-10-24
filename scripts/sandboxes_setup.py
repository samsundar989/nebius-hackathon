#!/usr/bin/env python3
"""Build the Juliet toolchain image on Nebius Sandboxes, once (D-0053).

Same toolchain as images/cpp-sanitizers (Ubuntu 24.04, clang-18 + ASan/UBSan/LSan runtimes,
libc++), installed with networking on in a saved run and tagged `lp-cpp-sanitizers`. Every
gate run that starts from it has networking off. Prints import/install times and the cost.
"""

from __future__ import annotations

import json
import sys
import time

from leakproof.config import RUNS_DIR
from leakproof.runner.sandboxes_rest import SandboxesRestRunner

TAG = "lp-cpp-sanitizers"
INSTALL = (
    "export DEBIAN_FRONTEND=noninteractive; apt-get update -q && apt-get install -y -q "
    "--no-install-recommends clang-18 llvm-18 libclang-rt-18-dev libc++-18-dev "
    "libc++abi-18-dev make coreutils ca-certificates > /tmp/apt.log 2>&1; rc=$?; "
    "tail -3 /tmp/apt.log; [ $rc = 0 ] || exit $rc; "
    "ln -sf /usr/bin/clang-18 /usr/bin/clang; ln -sf /usr/bin/clang++-18 /usr/bin/clang++; "
    "ln -sf /usr/bin/llvm-symbolizer-18 /usr/bin/llvm-symbolizer; "
    "rm -rf /var/lib/apt/lists/*; mkdir -p /work; clang --version | head -1"
)


def main() -> int:
    r = SandboxesRestRunner()
    t0 = time.monotonic()
    base = r.import_image("ubuntu:24.04")
    t1 = time.monotonic()
    res = r.run(base, INSTALL, cwd="/", network=True, save=True, timeout_s=1800)
    t2 = time.monotonic()
    if res.exit_code != 0 or res.image is None:
        print(res.stdout[-2000:], res.stderr[-2000:])
        return 1
    ref = r.tag(res.image, TAG)
    probe = r.run(ref, "clang --version | head -1; command -v llvm-symbolizer", network=False)
    out = {
        "tag": TAG,
        "image": res.image.ref,
        "import_s": round(t1 - t0, 1),
        "install_s": round(t2 - t1, 1),
        "install_cost": res.cost,
        "probe": probe.stdout.strip(),
        "lineage": r.lineage,
    }
    (RUNS_DIR / "sandboxes_setup.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
