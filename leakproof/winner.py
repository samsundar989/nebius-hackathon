"""Winner selection among several verified candidates (D-0070, replaces D-0039's smallest diff).

Every candidate passed the gate, so the gate cannot rank them. A knockout over the distinct
verified diffs, smallest first: Nemotron 3 Ultra compares champion and challenger ("which
preserves the original intent of the code"), asked in both orders; the challenger takes over
only when both orders prefer it, so a position-biased answer keeps the smaller diff. Ranking
signal only: it never changes a verdict. Sees the finding, root cause and the two diffs; never
the gate's corpus, tests or the developer's fix.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from leakproof.llm import LLMClient
from leakproof.llm.client import StructuredOutputError

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "prefer": {"type": "string", "enum": ["A", "B", "equal"]},
        "reason": {"type": "string"},
    },
    "required": ["prefer", "reason"],
    "additionalProperties": False,
}
SYSTEM = (
    "Two patches for the same memory-safety defect in C/C++ both stop the crash and pass every "
    "sanitizer and regression check. Which one would a maintainer merge? Prefer the patch that "
    "fixes the root cause and preserves the original intent of the code: the same objects keep "
    "the same data, valid inputs keep the same results, no work is silently skipped. Answer "
    "'equal' when neither is better. Give a 1-3 sentence reason citing the diffs."
)

Judge = Callable[[str, str], dict[str, Any]]


def ultra_judge(
    client: LLMClient, finding: dict[str, Any], root_cause: str, model: str = "ultra"
) -> Judge:
    def judge(a: str, b: str) -> dict[str, Any]:
        user = (
            f"Defect: {finding.get('kind', '?')} at {finding.get('location') or '?'}\n"
            f"Root cause (planner, may be wrong): {root_cause[:1500]}\n\n"
            f"Patch A:\n{a[:14000]}\n\nPatch B:\n{b[:14000]}"
        )
        try:
            value, res = client.structured(
                model,
                [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
                SCHEMA,
                purpose="select",
                thinking=True,
                max_completion_tokens=8000,
            )
        except StructuredOutputError as exc:
            return {"prefer": "equal", "reason": f"error: {str(exc)[:200]}", "usd": 0.0}
        return {"prefer": value["prefer"], "reason": value["reason"], "usd": res.usd}

    return judge


def choose(diffs: list[str], judge: Judge | None) -> tuple[str, list[dict[str, Any]]]:
    """The winning diff among distinct verified diffs, and the comparison log."""
    order = sorted(dict.fromkeys(diffs), key=len)
    champ, log = order[0], []
    if judge is None:
        return champ, log
    for chal in order[1:]:
        fwd = judge(champ, chal)  # challenger is B
        rev = judge(chal, champ)  # challenger is A
        switch = fwd["prefer"] == "B" and rev["prefer"] == "A"
        log.append(
            {
                "champion_chars": len(champ),
                "challenger_chars": len(chal),
                "forward": fwd,
                "reverse": rev,
                "switch": switch,
            }
        )
        if switch:
            champ = chal
    return champ, log
