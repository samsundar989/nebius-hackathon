#!/usr/bin/env python3
"""Summarize P1 calibration: the gate's verdict on each developer fix.

  scripts/calibration_report.py p1_calibration_v3   -> runs/<dir>/summary.json + markdown

Automatic ("raw") classes:
  accepted       developer fix verified
  false_reject   gated in full and not verified (a gate bug or harness quirk until explained)
  partial        the fix commit did not apply cleanly to the baseline: not counted
  out_of_scope   the fix is in the fuzz harness (no candidate may edit it): not counted
  no_candidate   no applicable fix commit / baseline failure: not counted
Adjudicated class: the raw class unless cases/arvo/calibration_adjudication.json (a reviewed,
evidence-linked note per case) overrides it; adds true_reject (the gate is right: the
developer fix itself has the defect it rejects). Both columns are always reported.
False-reject rate = false_reject / (accepted + false_reject + true_reject).
"""

from __future__ import annotations

import json
import sys
from collections import Counter

from leakproof.config import REPO_ROOT, RUNS_DIR

ADJUDICATION = REPO_ROOT / "cases" / "arvo" / "calibration_adjudication.json"
JUDGED = ("accepted", "false_reject", "true_reject")


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


def rate(counts: Counter) -> tuple[int, float | None]:
    judged = sum(counts[k] for k in JUDGED)
    return judged, (round(counts["false_reject"] / judged, 3) if judged else None)


def main(argv: list[str]) -> int:
    run = RUNS_DIR / argv[0]
    notes = json.loads(ADJUDICATION.read_text()) if ADJUDICATION.exists() else {}
    rows = []
    for path in sorted(run.glob("*/calibration.json")):
        rec = json.loads(path.read_text())
        meta = rec.get("dev_fix", {})
        raw = classify(rec)
        note = notes.get(rec["case"], {})
        rows.append(
            {
                "case": rec["case"],
                "project": rec.get("project"),
                "crash_type": rec.get("crash_type"),
                "raw_class": raw,
                "class": note.get("class", raw),
                "why": note.get("why", ""),
                "verdict": rec.get("dev", {}).get("verdict") or rec.get("error", "")[:120],
                "files": meta.get("files"),
                "diff_lines": meta.get("diff_lines"),
                "commits": len(meta.get("commits") or []),
                "elapsed_s": rec.get("elapsed_s"),
            }
        )
    raw_counts = Counter(r["raw_class"] for r in rows)
    counts = Counter(r["class"] for r in rows)
    raw_judged, raw_rate = rate(raw_counts)
    judged, adj_rate = rate(counts)
    summary = {
        "cases": len(rows),
        "raw": {"classes": dict(raw_counts), "judged": raw_judged, "false_reject_rate": raw_rate},
        "adjudicated": {"classes": dict(counts), "judged": judged, "false_reject_rate": adj_rate},
        "rows": rows,
    }
    (run / "summary.json").write_text(json.dumps(summary, indent=1))
    print("| case | project | crash type | gate on developer fix | raw | adjudicated |")
    print("|---|---|---|---|---|---|")
    for r in rows:
        v = r["verdict"].splitlines()[0][:70]
        print(
            f"| {r['case']} | {r['project']} | {r['crash_type']} | {v} | "
            f"{r['raw_class']} | {r['class']} |"
        )
    print(
        f"\nraw: {raw_counts['accepted']}/{raw_judged} accepted, false-reject rate {raw_rate}"
        f"\nadjudicated: {counts['accepted']}/{judged} accepted, {counts['true_reject']} true "
        f"reject(s), false-reject rate {adj_rate}; classes {dict(counts)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
