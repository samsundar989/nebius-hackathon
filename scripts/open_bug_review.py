#!/usr/bin/env python3
"""Ultra's review of every verified open-bug fix (review #6 order 1): no developer fix exists, so
each distinct verified diff is judged against the defect and the code around it.

scripts/open_bug_review.py RUN [RUN ...] -> runs/open_bugs/review.json (advisory; a human review
in cases/open_bugs/REVIEW.md decides what is ready to propose)
"""

from __future__ import annotations

import json
import sys
from typing import Any

from leakproof.config import RUNS_DIR, load_dotenv
from leakproof.llm import CostLedger, LLMClient
from leakproof.semantic import change, wide_diff

CLASSES = ("correct", "defensive", "wrong", "unsure")
SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "class": {"type": "string", "enum": list(CLASSES)},
        "reason": {"type": "string"},
    },
    "required": ["class", "reason"],
    "additionalProperties": False,
}
SYSTEM = (
    "You review a patch for a memory-safety defect in C/C++ found in an open-source project; "
    "no upstream fix exists yet. The patch stops the reported crash. Classes:\n"
    "- correct: fixes the cause for every input, keeps valid-input behaviour, a maintainer "
    "would merge it.\n"
    "- defensive: safe on the reported input but guards the symptom (padding, clamping, an "
    "early return) while the cause remains reachable or behaviour changes.\n"
    "- wrong: the cause remains reachable on other inputs, or the patch is itself incorrect "
    "(type confusion, undefined behaviour, broken valid inputs).\n"
    "- unsure: not enough context.\n"
    "Give 2-4 sentences naming the lines that decide it. Do not trust the planner's root cause "
    "blindly; check it against the code shown."
)


def main() -> int:
    load_dotenv()
    client = LLMClient(ledger=CostLedger(budget=0.3), run_id="open_bug_review")
    out = []
    for run in sys.argv[1:]:
        for p in sorted((RUNS_DIR / run).glob("*.json")):
            rec = json.loads(p.read_text())
            seen = set()
            for w in rec.get("workers", []):
                if w.get("verdict") != "verified" or change(w["diff"]) in seen:
                    continue
                seen.add(change(w["diff"]))
                f = rec["finding"]
                user = (
                    f"Defect: {f.get('kind')} at {f.get('location')}\n"
                    f"Planner's root cause (may be wrong): {rec['plan'].get('root_cause', '')[:1500]}\n\n"
                    f"Patch (30 lines of context):\n{wide_diff(w['files'], w['diff'])[:16000]}"
                )
                value, res = client.structured(
                    "ultra",
                    [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
                    SCHEMA,
                    purpose="open_bug_review",
                    thinking=True,
                    max_completion_tokens=12000,
                )
                row = {
                    "run": run,
                    "case": rec["case"].split("/")[-1],
                    "worker": f"{w['hypothesis_id']}·w{w['worker_index']}",
                    "winner": w["diff"] == (rec.get("winner") or {}).get("diff"),
                    "class": value["class"],
                    "reason": value["reason"],
                    "usd": res.usd,
                }
                out.append(row)
                print(json.dumps(row)[:400], flush=True)
    (RUNS_DIR / "open_bugs").mkdir(exist_ok=True)
    (RUNS_DIR / "open_bugs" / "review.json").write_text(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
