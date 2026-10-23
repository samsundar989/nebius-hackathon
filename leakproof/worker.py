"""Worker: Nemotron 3.5 Lightning turns one hypothesis into search/replace edits.

The worker sees the finding, the planner's hypothesis, and the source of the files it may edit.
It never sees the PoC, the tests, the corpus or the gate (this module must not import
leakproof.gate). Feedback it may get: an edit that did not apply, and compiler errors.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from leakproof.cases.base import BuildResult, Window
from leakproof.context import render_finding, render_windows
from leakproof.edits import EditError, apply_blocks, parse_blocks, unified_diff
from leakproof.llm import ChatResult, LLMClient

SYSTEM = """You fix one memory-safety defect in C/C++ code, following the plan you are given.

Reply with one or more edit blocks and nothing else. Each block names the file on its own line,
then SEARCH lines copied exactly from that file (enough lines to be unique), then the
replacement:

src/example.c
<<<<<<< SEARCH
    buf = malloc(len);
    memcpy(buf, src, len + 1);
=======
    buf = malloc(len + 1);
    memcpy(buf, src, len + 1);
>>>>>>> REPLACE

Rules:
- Edit only the files listed under "Files you may edit". Never touch tests, build files,
  sanitizer options or compiler flags.
- Do not hide the defect: no exiting early, no skipping the code path, no try/catch-style
  bypasses, no sanitizer attributes or annotations.
- Make the smallest change that removes the defect and keeps behavior on valid inputs.
- Lines like "/* [LEAKPROOF: ... omitted ...] */" stand for code you cannot see: keep each one
  exactly once and do not put it inside a SEARCH block.
- SEARCH text must match the file character for character, including indentation."""


@dataclass
class Candidate:
    hypothesis_id: str
    worker_index: int
    status: str = "pending"  # edited | no_edit | apply_failed | build_failed | built | error
    files: dict[str, str] = field(default_factory=dict)  # full restored text of edited files
    diff: str = ""
    apply_strategies: list[str] = field(default_factory=list)
    attempts: list[dict[str, Any]] = field(default_factory=list)
    build: dict[str, Any] | None = None
    usd: float = 0.0
    llm_s: float = 0.0
    elapsed_s: float = 0.0
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def _files_for(hypothesis: dict[str, Any], sources: dict[str, str]) -> list[str]:
    named = []
    for want in hypothesis.get("files", []):
        want = want.strip().lstrip("./")
        hits = [
            p
            for p in sources
            if p == want or p.endswith("/" + want) or p.split("/")[-1] == want.split("/")[-1]
        ]
        named += [h for h in hits if h not in named]
    return named or list(sources)


def build_messages(
    finding: dict[str, Any],
    root_cause: str,
    hypothesis: dict[str, Any],
    windows: list[Window],
    editable: list[str],
) -> list[dict[str, str]]:
    shown = [w for w in windows if w.path in editable]
    user = (
        f"## Finding\n{render_finding(finding)}\n\n"
        f"## Plan\nRoot cause: {root_cause}\nYour hypothesis ({hypothesis['strategy']}): "
        f"{hypothesis['summary']}\n\n"
        "## Files you may edit\n"
        + "\n".join(f"- {p}" for p in editable)
        + f"\n\n## Source\n{render_windows(shown)}"
    )
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]


def run_worker(
    client: LLMClient,
    *,
    index: int,
    finding: dict[str, Any],
    root_cause: str,
    hypothesis: dict[str, Any],
    sources: dict[str, str],
    windows: list[Window],
    restore: Callable[[str, str], str],
    build: Callable[[dict[str, str]], BuildResult] | None,
    model: str = "lightning",
    max_completion_tokens: int = 6_000,
    temperature: float = 0.6,
) -> Candidate:
    t0 = time.monotonic()
    cand = Candidate(hypothesis["id"], index)
    editable = _files_for(hypothesis, sources)
    messages = build_messages(finding, root_cause, hypothesis, windows, editable)
    allowed = {p: sources[p] for p in editable}
    feedback_rounds = {"apply": 0, "build": 0, "empty": 0}
    thinking = True

    def call(purpose: str) -> ChatResult:
        res = client.chat(
            model,
            messages,
            purpose=purpose,
            thinking=thinking,
            max_completion_tokens=max_completion_tokens,
            temperature=temperature,
        )
        cand.usd += res.usd
        cand.llm_s += res.latency_s
        cand.attempts.append(
            {
                "purpose": purpose,
                "thinking": thinking,
                "finish": res.finish_reason,
                "completion_tokens": res.completion_tokens,
                "reasoning_tokens": res.reasoning_tokens,
                "usd": round(res.usd, 6),
                "latency_s": round(res.latency_s, 2),
                "text": res.text[-4000:],
            }
        )
        return res

    try:
        res = call("worker")
        while True:
            try:
                blocks = parse_blocks(res.text)
                if not blocks:
                    raise EditError("no SEARCH/REPLACE blocks in the reply")
                edited, strategies = apply_blocks(allowed, blocks)
                full = {p: restore(p, t) for p, t in edited.items() if t != allowed[p]}
                if not full:
                    raise EditError("the edits do not change anything")
            except (EditError, ValueError) as exc:
                empty = not res.text.strip()
                key = "empty" if empty else "apply"
                if feedback_rounds[key] >= 1:
                    cand.status = "no_edit" if empty else "apply_failed"
                    cand.error = str(exc)
                    break
                feedback_rounds[key] += 1
                if empty:
                    thinking = False  # E0: reasoning spent the budget and no edit came out
                    res = call("worker:retry_no_thinking")
                else:
                    messages += [
                        {"role": "assistant", "content": res.text},
                        {
                            "role": "user",
                            "content": f"Your edit could not be applied: {exc}. "
                            "Reply again with corrected edit blocks only.",
                        },
                    ]
                    res = call("worker:apply_repair")
                continue
            cand.files, cand.apply_strategies, cand.status = full, strategies, "edited"
            originals = {p: restore(p, allowed[p]) for p in full}
            cand.diff = unified_diff(originals, full)
            if build is None:
                break
            b = build(full)
            cand.build = {"ok": b.ok, "elapsed_s": b.elapsed_s, "log_tail": b.log_tail[-2000:]}
            if b.ok:
                cand.status = "built"
                break
            if feedback_rounds["build"] >= 1:
                cand.status = "build_failed"
                break
            feedback_rounds["build"] += 1
            messages += [
                {"role": "assistant", "content": res.text},
                {
                    "role": "user",
                    "content": "The patched code does not compile:\n"
                    f"{b.log_tail[-2500:]}\nReply with corrected edit blocks against the "
                    "ORIGINAL source shown above.",
                },
            ]
            res = call("worker:build_repair")
    except Exception as exc:  # budget, API errors: recorded per worker, never fatal to the case
        cand.status, cand.error = "error", f"{type(exc).__name__}: {exc}"
    cand.usd = round(cand.usd, 6)
    cand.llm_s = round(cand.llm_s, 2)
    cand.elapsed_s = round(time.monotonic() - t0, 2)
    return cand
