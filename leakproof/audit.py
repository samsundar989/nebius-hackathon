"""Gate check 8: an LLM review of each gated diff. Flags only: stored next to the verdict, never
changes it (the sanitizer and test evidence decide). Lightning, thinking off (D-0051).

The six checks are generic code-review questions for memory-safety patches; the reviewer sees
the finding and the diff, nothing from the gate (no corpus, no fuzz settings, no verdict).
"""

from __future__ import annotations

from typing import Any

from leakproof.llm import LLMClient
from leakproof.llm.client import StructuredOutputError

CHECKS = {
    "root_cause": "Does the change fix the cause of the defect, not just the line that crashed?",
    "silencing": (
        "Does it hide the error instead (early return or skip that drops real work, a clamp "
        "or bounds check that discards data, catching and ignoring a failure)?"
    ),
    "new_memory_risk": (
        "Could it add a leak, use-after-free, double free, overflow, or uninitialized read?"
    ),
    "behavior_change": "Does it change behavior for valid inputs or the public API?",
    "error_handling": (
        "Are new failure paths consistent with the code around them (return codes, cleanup, "
        "messages)?"
    ),
    "scope": "Does it edit anything unrelated (other functions, comments, formatting)?",
}
SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        name: {
            "type": "object",
            "properties": {"flag": {"type": "boolean"}, "note": {"type": "string"}},
            "required": ["flag", "note"],
            "additionalProperties": False,
        }
        for name in CHECKS
    },
    "required": list(CHECKS),
    "additionalProperties": False,
}
SYSTEM = (
    "You review a patch for a memory-safety defect in C/C++. For each question answer flag=true "
    "when the answer is a concern (root_cause: true means it does NOT fix the cause; scope: "
    "true means it edits unrelated code), with a one-sentence note citing the diff. Do not "
    "speculate beyond the diff."
)


def audit(
    client: LLMClient,
    finding: dict[str, Any],
    diff: str,
    *,
    model: str = "lightning",
    max_completion_tokens: int = 1200,
) -> dict[str, Any]:
    questions = "\n".join(f"- {k}: {q}" for k, q in CHECKS.items())
    where = finding.get("location") or "?"
    user = (
        f"Defect: {finding.get('kind', '?')} at {where}\n{finding.get('summary', '')[:400]}\n\n"
        f"Questions:\n{questions}\n\nDiff:\n{diff[:12000]}"
    )
    try:
        value, res = client.structured(
            model,
            [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
            SCHEMA,
            purpose="audit",
            thinking=False,
            max_completion_tokens=max_completion_tokens,
        )
    except StructuredOutputError as exc:
        return {"error": str(exc)[:300], "flags": [], "model": model}
    return {
        "checks": value,
        "flags": [k for k in CHECKS if value[k]["flag"]],
        "model": res.model,
        "usd": res.usd,
    }
