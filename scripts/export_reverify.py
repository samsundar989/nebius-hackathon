#!/usr/bin/env python3
"""Stored candidates for the demo's "Re-verify without AI" button (review #17 order 4).

For every case on the demo's allow-list (service/juliet/cases.txt), copies two worker candidates
from real run records into service/reverify/<case>.json: one the gate verified and, where a run
has one, one it rejected. Each keeps the full edited files, the diff, the run it came from and
the verdict the gate gave then, so the service can re-run the gate on it with no model call and
show whether today's verdict matches.
"""

from __future__ import annotations

import json
import sys

from leakproof.config import REPO_ROOT, RUNS_DIR

OUT = REPO_ROOT / "service" / "reverify"
ALLOWED = (REPO_ROOT / "service" / "juliet" / "cases.txt").read_text().split()
# Rejections that show the gate catching a patch that looks plausible come first.
REJECT_ORDER = (
    "silenced_only",
    "rejected:new_leak",
    "rejected:new_double-free",
    "rejected:still_crashes",
    "rejected:diff_scope",
)


def stored(w: dict, rec: dict, src: str) -> dict:
    strategy = {h["id"]: h.get("strategy", "other") for h in rec["plan"]["hypotheses"]}
    return {
        "hypothesis_id": w["hypothesis_id"],
        "worker_index": w["worker_index"],
        "strategy": strategy.get(w["hypothesis_id"], "other"),
        "files": w["files"],
        "diff": w["diff"],
        "verdict_then": w["verdict"],
        "source": src,
    }


def main() -> int:
    OUT.mkdir(exist_ok=True)
    for case in ALLOWED:
        ok, bad = [], []
        # Smoke runs predate the gate's fixed behaviour check (one correct leak fix there was
        # judged silenced_only); only runs gated by the current checks are compared.
        for p in sorted(RUNS_DIR.glob(f"*/{case}.json")):
            if p.parent.name.startswith("smoke_"):
                continue
            rec = json.loads(p.read_text())
            src = p.relative_to(REPO_ROOT).as_posix()
            for w in rec.get("workers", []):
                if w.get("status") != "built" or not w.get("files"):
                    continue
                (ok if w["verdict"] == "verified" else bad).append(stored(w, rec, src))
        if not ok:
            print(f"{case}: no verified candidate", file=sys.stderr)
            continue
        out = {"case": case, "verified": min(ok, key=lambda c: len(c["diff"]))}
        bad = [c for c in bad if c["verdict_then"] in REJECT_ORDER]
        if bad:
            out["rejected"] = min(bad, key=lambda c: REJECT_ORDER.index(c["verdict_then"]))
        (OUT / f"{case}.json").write_text(json.dumps(out, indent=1) + "\n")
        print(case, "verified", "+ " + out["rejected"]["verdict_then"] if bad else "")
    return 0


if __name__ == "__main__":
    sys.exit(main())
