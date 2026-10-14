#!/usr/bin/env python3
"""ARVO probe (kickoff 3.6): pull 3 `-vul` images, reproduce, parse, time a rebuild.

Per case: metadata from arvo.db (release v3.0.0) -> `docker pull` (timed) -> run `arvo`
(PoC against the shipped harness, network off) -> parse the report -> `arvo compile` (rebuild
from source, timed) -> `arvo` again -> rebuild with our leak-sensitive flags (-O0) -> `arvo`.
The `-fix` image is checked on Docker Hub, not pulled. No fixes are attempted.

Writes cases/arvo/<id>.json and tests/fixtures/arvo/<id>.log.
Usage: uv run python scripts/arvo_probe.py [--ids 42493685,42508415,42492467] [--skip-rebuild]
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from leakproof.findings import parse_report, primary
from leakproof.runner import ImageRef, LocalDockerRunner

ROOT = Path(__file__).resolve().parent.parent
DB = Path.home() / ".cache" / "leakproof" / "arvo" / "arvo.db"
DEFAULT_IDS = "42493685,42508415,42492467"
OUR_FLAGS = "-O0 -gline-tables-only -DFUZZING_BUILD_MODE_UNSAFE_FOR_PRODUCTION"


def meta(local_id: int) -> dict:
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    row = con.execute("select * from arvo where localId = ?", (local_id,)).fetchone()
    if row is None:
        raise SystemExit(f"{local_id} not in arvo.db")
    keep = [
        "localId",
        "project",
        "crash_type",
        "fuzz_target",
        "fuzz_engine",
        "sanitizer",
        "severity",
        "fix_commit",
        "patch_url",
        "repo_addr",
        "language",
        "report",
    ]
    return {k: row[k] for k in keep}


def hub_tag(tag: str) -> dict | None:
    url = f"https://hub.docker.com/v2/repositories/n132/arvo/tags/{tag}"
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            d = json.load(resp)
        return {"compressed_bytes": d.get("full_size"), "last_updated": d.get("last_updated")}
    except OSError:
        return None


def timed(fn):  # noqa: ANN001, ANN201
    t0 = time.monotonic()
    out = fn()
    return out, round(time.monotonic() - t0, 1)


def probe(local_id: int, rebuild: bool) -> dict:
    m = meta(local_id)
    image = f"n132/arvo:{local_id}-vul"
    present = (
        subprocess.run(["docker", "image", "inspect", image], capture_output=True).returncode == 0
    )
    _, pull_s = timed(
        lambda: subprocess.run(["docker", "pull", "-q", image], check=True, capture_output=True)
    )
    size = subprocess.run(
        ["docker", "image", "inspect", "-f", "{{.Size}}", image],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    # build.sh is relative to the image WORKDIR (e.g. /src/md4c). Contree drops WORKDIR on
    # import and our runner sets cwd explicitly, so the case must carry it.
    workdir = (
        subprocess.run(
            ["docker", "image", "inspect", "-f", "{{.Config.WorkingDir}}", image],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        or "/src"
    )
    runner = LocalDockerRunner(memory="4g", cpus=2)
    ref = ImageRef("docker", image)
    repro = runner.run(ref, "arvo", cwd=workdir, timeout_s=300, network=False)
    findings = parse_report(repro.stderr + repro.stdout)
    p = primary(findings)
    rec: dict = {
        "id": str(local_id),
        **{k: v for k, v in m.items() if k != "report"},
        "oss_fuzz_report": m["report"],
        "image_vul": image,
        "image_fix": f"n132/arvo:{local_id}-fix",
        "fix_image_on_hub": hub_tag(f"{local_id}-fix"),
        "vul_image_on_hub": hub_tag(f"{local_id}-vul"),
        "pull_s": pull_s,
        "pull_was_cached": present,
        "image_bytes_local": int(size),
        "repro_cmd": "arvo",
        "repro_exit": repro.exit_code,
        "repro_s": repro.elapsed_s,
        "reproduced": repro.exit_code != 0 and p is not None,
        "finding": p.to_dict(include_raw=False) if p else None,
        "all_kinds": [f.kind for f in findings],
        "harness": f"/out/{m['fuzz_target']}",
        "poc": "/tmp/poc",
        "source_dir": f"/src/{m['project']}",
        "workdir": workdir,
    }
    (ROOT / "tests" / "fixtures" / "arvo").mkdir(parents=True, exist_ok=True)
    (ROOT / "tests" / "fixtures" / "arvo" / f"{local_id}.log").write_text(
        repro.stderr + repro.stdout
    )
    if rebuild:
        rb = runner.run(
            ref,
            "arvo compile > /tmp/compile.log 2>&1; rc=$?; tail -5 /tmp/compile.log; "
            "[ $rc = 0 ] && arvo",
            cwd=workdir,
            timeout_s=1800,
            network=False,
        )
        rb_p = primary(parse_report(rb.stderr + rb.stdout))
        rec.update(
            rebuild_s=rb.elapsed_s,
            rebuild_reproduces=rb_p is not None and p is not None and rb_p.kind == p.kind,
            rebuild_peak_kb=rb.max_rss_kb,
        )
        ours = runner.run(
            ref,
            f'export CFLAGS="{OUR_FLAGS}" CXXFLAGS="{OUR_FLAGS} -stdlib=libc++"; '
            "arvo compile > /tmp/compile.log 2>&1; rc=$?; tail -5 /tmp/compile.log; [ $rc = 0 ] && arvo",
            cwd=workdir,
            timeout_s=1800,
            network=False,
        )
        ours_p = primary(parse_report(ours.stderr + ours.stdout))
        rec.update(
            our_flags=OUR_FLAGS,
            our_flags_rebuild_s=ours.elapsed_s,
            our_flags_reproduces=ours_p is not None and p is not None and ours_p.kind == p.kind,
            our_flags_kind=ours_p.kind if ours_p else None,
            our_flags_location=ours_p.location if ours_p else None,
        )
    (ROOT / "cases" / "arvo").mkdir(parents=True, exist_ok=True)
    (ROOT / "cases" / "arvo" / f"{local_id}.json").write_text(json.dumps(rec, indent=1) + "\n")
    return rec


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", default=DEFAULT_IDS)
    ap.add_argument("--skip-rebuild", action="store_true")
    args = ap.parse_args()
    for local_id in args.ids.split(","):
        r = probe(int(local_id), rebuild=not args.skip_rebuild)
        f = r["finding"] or {}
        print(
            json.dumps(
                {
                    k: r.get(k)
                    for k in (
                        "id",
                        "project",
                        "crash_type",
                        "pull_s",
                        "image_bytes_local",
                        "repro_exit",
                        "repro_s",
                        "reproduced",
                        "rebuild_s",
                        "rebuild_reproduces",
                        "our_flags_rebuild_s",
                        "our_flags_reproduces",
                        "our_flags_location",
                    )
                }
                | {
                    "kind": f.get("kind"),
                    "location": f.get("location"),
                    "fix_on_hub": bool(r["fix_image_on_hub"]),
                }
            ),
            flush=True,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
