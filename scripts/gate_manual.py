#!/usr/bin/env python3
"""Gate hand-written or stored candidates for a bring-your-own project (no model calls).

scripts/gate_manual.py --config cases/.../leakproof.toml --out runs/<name> \
    --patch M1=path/to/one.diff --from-record H2w1=runs/<run>/<case>.json:H2:1

Each candidate is a unified diff applied to the case's source tree (patch -p1 semantics against
the paths in the diff) or a stored worker's files; the gate then judges all of them exactly as in
a `leakproof fix` run (tests, reproducer, and checks 5-7 when a harness exists).
Writes <out>/candidates.json and <out>/gate.json. Needs Docker: submit through workerq.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from leakproof.cases.project import ProjectCase
from leakproof.edits import unified_diff
from leakproof.fix import run_gate_process
from leakproof.runner import LocalDockerRunner


def from_patch(case: ProjectCase, diff_path: Path) -> dict[str, str]:
    """Apply a -p1 diff to a temporary copy of the touched files; container paths -> new text."""
    diff = diff_path.read_text(encoding="utf-8")
    rel = [ln[6:].strip() for ln in diff.splitlines() if ln.startswith("+++ b/")]
    with tempfile.TemporaryDirectory() as tmp:
        for r in rel:
            dst = Path(tmp) / r
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes((case.root / r).read_bytes())
        subprocess.run(["git", "apply", str(diff_path.resolve())], cwd=tmp, check=True)
        return {f"{case.workdir}/{r}": (Path(tmp) / r).read_text(encoding="utf-8") for r in rel}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--patch", action="append", default=[], help="ID=path/to/diff (-p1)")
    ap.add_argument("--from-record", action="append", default=[], help="ID=record.json:HYP:WORKER")
    args = ap.parse_args()
    case = ProjectCase.load(f"project:{args.config.resolve()}")
    cands = []
    for spec in args.patch:
        cid, path = spec.split("=", 1)
        files = from_patch(case, Path(path))
        originals = {
            p: (case.root / p[len(case.workdir) + 1 :]).read_text(encoding="utf-8") for p in files
        }
        cands.append(
            {
                "hypothesis_id": cid,
                "worker_index": 0,
                "strategy": "other",
                "files": files,
                "diff": unified_diff(originals, files),
            }
        )
    for spec in args.from_record:
        cid, ref = spec.split("=", 1)
        rec_path, hyp, idx = ref.rsplit(":", 2)
        rec = json.loads(Path(rec_path).read_text())
        w = next(
            w for w in rec["workers"] if (w["hypothesis_id"], w["worker_index"]) == (hyp, int(idx))
        )
        cands.append(
            {
                "hypothesis_id": cid,
                "worker_index": 0,
                "strategy": "other",
                "files": w["files"],
                "diff": w["diff"],
            }
        )
    args.out.mkdir(parents=True, exist_ok=True)
    runner = LocalDockerRunner(memory="4g", cpus=2)
    try:
        baseline = case.prepare(runner)
        gate = run_gate_process(case.id, baseline.ref, case.workdir, case.finding, cands, args.out)
    finally:
        case.cleanup(runner)
    for r in gate["results"]:
        print(
            r["hypothesis_id"],
            r["verdict"],
            {k: (v["status"], v["detail"][:120]) for k, v in r["checks"].items()},
            flush=True,
        )
    print("tests on baseline:", gate.get("tests_baseline"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
