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
from leakproof.context import render_finding, render_windows, shown_ranges
from leakproof.edits import EditError, apply_blocks, parse_blocks, parse_unified, unified_diff
from leakproof.llm import ChatResult, LLMClient

SYSTEM = """You fix one memory-safety defect in C/C++ code, following the plan you are given.

Reply with one or more edit blocks and nothing else. Each block names the file on its own line,
then SEARCH lines copied exactly from that file (enough lines to be unique), then the
replacement:

path/of/the/file.c
<<<<<<< SEARCH
<the lines to change, copied from that file>
=======
<the new lines>
>>>>>>> REPLACE

Rules:
- Edit only the files listed under "Files you may edit". Never touch tests, build files,
  sanitizer options or compiler flags.
- Do not hide the defect: no exiting early, no skipping the code path, no try/catch-style
  bypasses, no sanitizer attributes or annotations.
- Make the smallest change that removes the defect and keeps behavior on valid inputs.
- Lines like "/* [LEAKPROOF: ... omitted ...] */" stand for code you cannot see: keep each one
  exactly once and do not put it inside a SEARCH block.
- SEARCH lines are matched ignoring indentation and spacing: copy the code lines as shown and
  do not spend effort counting spaces. Use the real file name from "Files you may edit".
  Source is shown with line numbers ("  120| code"); do not copy the numbers into SEARCH.
- Think briefly. The fix is usually a few lines; reply with the edit blocks as soon as you
  know the change.

If you cannot quote the lines exactly, two other forms work (prefer SEARCH/REPLACE):

@@ replace path/of/the/file.c lines 120-134 @@
<new text for exactly those shown lines>
@@ end @@

@@ function name_of_function in path/of/the/file.c @@
<the complete new definition of that function>
@@ end @@"""
NO_THINKING_RETRY = (
    "Reply now with the edit blocks only: no explanation, no reasoning, no restating the code. "
    "If SEARCH text is hard to reproduce, use the '@@ replace <file> lines A-B @@' form."
)


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
    # Line-range edits may only replace lines the worker was actually shown.
    shown = shown_ranges([w for w in windows if w.path in editable])
    feedback_rounds = {"apply": 0, "build": 0, "empty": 0}
    thinking = True

    def call(purpose: str, cap: int | None = None) -> ChatResult:
        res = client.chat(
            model,
            messages,
            purpose=purpose,
            thinking=thinking,
            max_completion_tokens=min(cap or max_completion_tokens, max_completion_tokens),
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
            blocks_seen = False
            try:
                blocks = parse_blocks(res.text, complete=res.finish_reason != "length")
                if not blocks:
                    blocks = parse_unified(res.text)  # a diff instead of edit blocks (D-0065)
                blocks_seen = bool(blocks)
                if not blocks:
                    raise EditError("no edit blocks in the reply")
                edited, strategies = apply_blocks(allowed, blocks, shown)
                full = {p: restore(p, t) for p, t in edited.items() if t != allowed[p]}
                if not full:
                    raise EditError("the edits do not change anything")
            except (EditError, ValueError) as exc:
                # No reply, or reasoning that ran into the token cap before any edit (E0/E1).
                empty = not res.text.strip() or (res.finish_reason == "length" and not blocks_seen)
                key = "empty" if empty else "apply"
                if feedback_rounds[key] >= 1:
                    cand.status = "no_edit" if empty else "apply_failed"
                    cand.error = str(exc)
                    break
                feedback_rounds[key] += 1
                if empty:
                    # E0/P3: reasoning spent the budget and no edit came out. Without thinking
                    # the model reasons in the reply instead (P3: 11 replies ran to 12K), so
                    # ask for blocks only and cap the reply.
                    thinking = False
                    messages += [{"role": "user", "content": NO_THINKING_RETRY}]
                    res = call("worker:retry_no_thinking", cap=4_000)
                else:
                    messages += [
                        {"role": "assistant", "content": res.text[-6000:]},
                        {
                            "role": "user",
                            "content": f"Your edit could not be applied: {exc}. Reply again "
                            "with corrected edit blocks only. If the SEARCH text keeps "
                            "failing, use '@@ replace <file> lines A-B @@' with the line "
                            "numbers shown in the source.",
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
