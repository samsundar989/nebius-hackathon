#!/usr/bin/env python3
"""Download NIST SARD Juliet C/C++ 1.3 (test suite 112, public domain) and extract the CWEs we use.

Keeps everything Linux-side under ~/.cache/leakproof/juliet (not under /mnt/c).
Usage: uv run python scripts/juliet_fetch.py [--cwes 401,415,416]
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

URL = (
    "https://samate.nist.gov/SARD/downloads/test-suites/"
    "2017-10-01-juliet-test-suite-for-c-cplusplus-v1-3.zip"
)
EXPECTED_BYTES = 152_957_342
CACHE = Path.home() / ".cache" / "leakproof" / "juliet"


def fetch(dest: Path) -> float:
    if dest.exists() and dest.stat().st_size == EXPECTED_BYTES:
        return 0.0
    dest.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.monotonic()
    tmp = dest.with_suffix(".part")
    # samate.nist.gov returns 403 to Python's default User-Agent.
    req = urllib.request.Request(URL, headers={"User-Agent": "leakproof-juliet-fetch/0.1"})
    with urllib.request.urlopen(req, timeout=120) as resp, tmp.open("wb") as fh:
        while chunk := resp.read(1 << 20):
            fh.write(chunk)
    if tmp.stat().st_size != EXPECTED_BYTES:
        raise SystemExit(f"size mismatch: got {tmp.stat().st_size}, want {EXPECTED_BYTES}")
    tmp.rename(dest)
    return time.monotonic() - t0


def extract(zip_path: Path, out: Path, cwes: list[str]) -> int:
    prefixes = ["C/testcasesupport/"] + [f"C/testcases/CWE{c}_" for c in cwes]
    n = 0
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            if any(info.filename.startswith(p) for p in prefixes) and not info.is_dir():
                target = out / info.filename
                if not target.exists():
                    zf.extract(info, out)
                n += 1
    return n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cwes", default="401,415,416")
    args = ap.parse_args()
    zip_path = CACHE / "juliet-c-cpp-v1.3.zip"
    secs = fetch(zip_path)
    sha = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    n = extract(zip_path, CACHE, args.cwes.split(","))
    print(f"zip {zip_path} ({zip_path.stat().st_size} B, sha256 {sha}) download {secs:.1f}s")
    print(f"extracted {n} files under {CACHE / 'C'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
