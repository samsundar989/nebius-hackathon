#!/usr/bin/env python3
"""Run cases/cuda/run_samples.sh on a Kaggle GPU (private script kernel, no internet needed).

The local RTX 5090 cannot host compute-sanitizer under WSL2 (WDDM debugger interface disabled;
CUDA 12.6 does not support sm_120), so the CUDA sanity check runs on Kaggle's native-Linux GPU.
The kernel embeds the two samples and the run script; nothing else from the repo is uploaded.

Usage: uv run python scripts/kaggle_cuda.py [--user neopok919] [--out runs/kaggle_cuda]
Needs ~/.kaggle/kaggle.json (or access_token). The Kaggle CLI is run through `uvx kaggle`.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CASES = ROOT / "cases" / "cuda"
SLUG = "leakproof-cuda-sanitizer-e0"

KERNEL = """\
import json, os, subprocess, pathlib
files = json.loads({payload!r})
src = pathlib.Path("/kaggle/working/cases"); src.mkdir(parents=True, exist_ok=True)
for name, body in files.items():
    (src / name).write_text(body)
env = dict(os.environ)
env["PATH"] = "/usr/local/cuda/bin:/usr/local/cuda/compute-sanitizer:" + env.get("PATH", "")
r = subprocess.run(["bash", str(src / "run_samples.sh"), str(src), "/kaggle/working/out"],
                   env=env, capture_output=True, text=True)
log = r.stdout + "\\n--- stderr ---\\n" + r.stderr + f"\\nrun_samples exit={{r.returncode}}\\n"
pathlib.Path("/kaggle/working/run_samples.log").write_text(log)
print(log)
"""


def kaggle(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["uvx", "kaggle", *args],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--user", default="neopok919")
    ap.add_argument("--out", type=Path, default=ROOT / "runs" / "kaggle_cuda")
    ap.add_argument("--timeout-min", type=int, default=30)
    args = ap.parse_args()

    payload = json.dumps(
        {p.name: p.read_text() for p in [*CASES.glob("*.cu"), CASES / "run_samples.sh"]}
    )
    with tempfile.TemporaryDirectory() as tmp:
        kdir = Path(tmp)
        (kdir / "run.py").write_text(KERNEL.format(payload=payload))
        meta = {
            "id": f"{args.user}/{SLUG}",
            "title": SLUG,
            "code_file": "run.py",
            "language": "python",
            "kernel_type": "script",
            "is_private": True,
            "enable_gpu": True,
            "enable_internet": False,
            "dataset_sources": [],
            "competition_sources": [],
            "kernel_sources": [],
        }
        (kdir / "kernel-metadata.json").write_text(json.dumps(meta, indent=1))
        t0 = time.time()
        push = kaggle("kernels", "push", "-p", str(kdir))
        print(push.stdout.strip(), push.stderr.strip(), sep="\n", flush=True)
        if push.returncode != 0:
            return 1

    deadline = time.time() + args.timeout_min * 60
    status = ""
    while time.time() < deadline:
        time.sleep(20)
        status = kaggle("kernels", "status", f"{args.user}/{SLUG}").stdout.strip()
        if any(s in status.lower() for s in ("complete", "error", "cancel")):
            break
    print(f"status after {time.time() - t0:.0f}s: {status}")
    args.out.mkdir(parents=True, exist_ok=True)
    got = kaggle("kernels", "output", f"{args.user}/{SLUG}", "-p", str(args.out), "-o")
    print(got.stdout.strip()[-500:], got.stderr.strip()[-500:], sep="\n")
    log = args.out / "run_samples.log"
    if log.exists():
        print(log.read_text())
    return 0 if "complete" in status.lower() else 1


if __name__ == "__main__":
    sys.exit(main())
