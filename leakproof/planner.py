"""Planner: Nemotron 3 Ultra reads the finding and the crashing code and ranks fix hypotheses.

Output is structured (D-0012: strings and enums only, no free numbers). It never sees the gate's
inputs: no PoC bytes, no test suite, no corpus, no re-fuzz settings.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from leakproof.cases.base import Window
from leakproof.context import render_finding, render_windows
from leakproof.llm import ChatResult, LLMClient

STRATEGIES = [
    "add_free",
    "remove_free",
    "bounds_check",
    "null_check",
    "lifetime_fix",
    "size_fix",
    "init",
    "other",
]
MAX_HYPOTHESES = 4

SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["root_cause", "cwe", "hypotheses"],
    "properties": {
        "root_cause": {"type": "string"},
        "cwe": {"type": "string"},
        "hypotheses": {
            "type": "array",
            "minItems": 1,
            "maxItems": MAX_HYPOTHESES,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "summary", "files", "strategy", "risk"],
                "properties": {
                    "id": {"type": "string"},
                    "summary": {"type": "string"},
                    "files": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                    "strategy": {"type": "string", "enum": STRATEGIES},
                    "risk": {"type": "string", "enum": ["low", "medium", "high"]},
                },
            },
        },
    },
}

SYSTEM = (
    "You are the planner of an automated repair system for memory-safety defects in C/C++. "
    "A sanitizer reproduced the defect below. Find the root cause (where the program's logic "
    "goes wrong, which is often not the crashing line) and propose up to "
    f"{MAX_HYPOTHESES} distinct fix hypotheses, best first. Each hypothesis is handed to a "
    "separate engineer who can edit only the files you name, so name every file the change "
    "needs and describe the change concretely (function, variable, condition). Prefer the "
    "smallest change that removes the defect while keeping behavior on valid inputs. Never "
    "propose silencing the sanitizer, changing build flags or tests, or exiting early to skip "
    "the faulty code. Diverse strategies beat four variants of one idea, but do not pad: one "
    "strong hypothesis is fine."
)


@dataclass
class Plan:
    root_cause: str
    cwe: str
    hypotheses: list[dict[str, Any]]
    model: str
    usd: float
    latency_s: float
    reasoning_tokens: int
    completion_tokens: int

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


REPAIR = (
    "\n\nThis is a repair round: earlier attempts were not verified. Their diffs and the "
    "reasons are below. Do not repeat a rejected approach; explain in root_cause what the "
    "earlier attempts missed, and propose hypotheses that address it."
)
WHOLE_FILE_CHARS = 240_000  # ~60K tokens of whole files on repair rounds (Ultra: 1M context)


def build_messages(
    finding: dict[str, Any],
    windows: list[Window],
    files: list[str],
    build: str,
    history: str | None = None,
    whole_files: dict[str, str] | None = None,
    notes: str | None = None,
) -> list[dict[str, str]]:
    user = (
        f"## Finding\n{render_finding(finding)}\n\n## Build and tests\n{build}\n\n"
        f"## Files you may name\n"
        + "\n".join(f"- {f}" for f in files)
        + f"\n\n## Source\n{render_windows(windows)}"
    )
    budget = WHOLE_FILE_CHARS
    for path, text in (whole_files or {}).items():
        if len(text) > budget:
            text = text[:budget] + "\n/* [file truncated: context budget] */"
        budget -= len(text)
        numbered = "\n".join(f"{i:>5}| {ln}" for i, ln in enumerate(text.splitlines(), 1))
        user += f"\n\n## Whole file {path}\n{numbered}"
        if budget <= 0:
            break
    if notes:
        # A person's review of earlier runs (`fix --notes`): prose about diffs, never gate inputs.
        user += f"\n\n## Reviewer notes on earlier runs\n{notes}"
    if history:
        user += f"\n\n## Earlier attempts and why they were not verified\n{history}"
    system = SYSTEM + (REPAIR if history else "")
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def plan(
    client: LLMClient,
    finding: dict[str, Any],
    windows: list[Window],
    files: list[str],
    build: str,
    *,
    model: str = "ultra",
    max_completion_tokens: int = 16_000,
    history: str | None = None,
    whole_files: dict[str, str] | None = None,
    notes: str | None = None,
) -> Plan:
    value, res = client.structured(
        model,
        build_messages(finding, windows, files, build, history, whole_files, notes),
        SCHEMA,
        purpose="planner:repair" if history else "planner",
        thinking=True,
        max_completion_tokens=max_completion_tokens,
    )
    hyps = value["hypotheses"][:MAX_HYPOTHESES]
    for i, h in enumerate(hyps):
        h["id"] = f"H{i + 1}"
    return _to_plan(value, hyps, res)


def _to_plan(value: dict[str, Any], hyps: list[dict[str, Any]], res: ChatResult) -> Plan:
    return Plan(
        value["root_cause"],
        value["cwe"],
        hyps,
        res.model,
        round(res.usd, 6),
        round(res.latency_s, 2),
        res.reasoning_tokens,
        res.completion_tokens,
    )


def no_planner_hypotheses(
    finding: dict[str, Any], files: list[str], n: int
) -> list[dict[str, Any]]:
    """Leaderboard baseline 'Lightning only': N workers get the finding and no plan."""
    return [
        {
            "id": f"H{i + 1}",
            "summary": "No plan given: diagnose the finding yourself and fix the root cause.",
            "files": files,
            "strategy": "other",
            "risk": "medium",
        }
        for i in range(n)
    ]
