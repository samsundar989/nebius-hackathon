#!/usr/bin/env python3
"""Summarize P1 calibration: the gate's verdict on each developer fix.

  scripts/calibration_report.py p1_calibration   -> runs/<dir>/summary.json + a markdown table

Classes:
  accepted       developer fix verified
  false_reject   gated in full and not verified (a gate bug or harness quirk until explained)
  partial        the fix commit did not apply cleanly to the baseline: not counted
  out_of_scope   the fix is in the fuzz harness (no candidate may edit it): not counted
  no_candidate   no applicable fix commit / baseline failure: not counted
False-reject rate = false_reject / (accepted + false_reject).
"""

from __future__ import annotations

import json
import sys
from collections import Counter

from leakproof.config import RUNS_DIR


def classify(rec: dict) -> str:
    if rec.get("error"):
        return "no_candidate"
    meta = rec.get("dev_fix", {})
    verdict = rec.get("dev", {}).get("verdict", "")
    if verdict.startswith("no_candidate"):
        return "out_of_scope" if "out_of_scope" in verdict else "no_candidate"
    if meta.get("partial"):
        return "partial"
    return "accepted" if verdict == "verified" else "false_reject"


def main(argv: list[str]) -> int:
    run = RUNS_DIR / argv[0]
    rows = []
    for path in sorted(run.glob("*/calibration.json")):
        rec = json.loads(path.read_text())
        meta = rec.get("dev_fix", {})
        rows.append(
            {
                "case": rec["case"],
                "project": rec.get("project"),
                "crash_type": rec.get("crash_type"),
                "class": classify(rec),
                "verdict": rec.get("dev", {}).get("verdict") or rec.get("error", "")[:120],
                "files": meta.get("files"),
                "diff_lines": meta.get("diff_lines"),
                "commits": len(meta.get("commits") or []),
                "elapsed_s": rec.get("elapsed_s"),
            }
        )
    counts = Counter(r["class"] for r in rows)
    judged = counts["accepted"] + counts["false_reject"]
    summary = {
        "cases": len(rows),
        "classes": dict(counts),
        "false_reject_rate": round(counts["false_reject"] / judged, 3) if judged else None,
        "rows": rows,
    }
    (run / "summary.json").write_text(json.dumps(summary, indent=1))
    print("| case | project | crash type | developer fix | class |\n|---|---|---|---|---|")
    for r in rows:
        print(
            f"| {r['case']} | {r['project']} | {r['crash_type']} | {r['verdict']} | {r['class']} |"
        )
    print(
        f"\n{counts['accepted']}/{judged} developer fixes accepted; "
        f"false-reject rate {summary['false_reject_rate']}; classes {dict(counts)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
