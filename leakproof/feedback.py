"""Round-1 failure summaries for the repair round (strategist order B2, D-0059).

Worker side: this module never imports the gate. It reads the gate's *results* (verdicts,
check details, saved sanitizer reports) and passes on only what the rule allows:
- compiler errors;
- "the PoC still crashes" / "a new crash" as kind + stack frames, re-rendered from parsed
  reports, never raw text (libFuzzer logs print the crashing input; it must not reach a model);
- "new leak" with its allocation stack;
- "behaviour changed on a corpus input" and "the project's tests fail" without the input,
  the corpus or the test output.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from leakproof.findings import parse_report, primary

MAX_FRAMES = 6
_SITE = re.compile(r"^(?P<what>[\w-]+ at [^;(]+?)(?: from |;|$)")


def _frames(report: str, which: str = "frames") -> str:
    """Top in-project frames of the first parsed finding, as `function file:line` lines."""
    f = primary(parse_report(report or ""))
    if f is None:
        return ""
    stack = getattr(f, which) or f.frames
    keep = [fr for fr in stack if fr.file and not fr.is_runtime][:MAX_FRAMES]
    head = f"{f.kind}" + (f" ({f.access} of size {f.access_size})" if f.access else "")
    return head + "".join(f"\n      at {fr.function} {fr.file}:{fr.line}" for fr in keep)


def _saved_report(artifacts: list[str]) -> str:
    """The gate's saved report next to a crash input (.log), never the input (.bin) itself."""
    for path in artifacts:
        if path.endswith(".log") and Path(path).exists():
            return Path(path).read_text(encoding="utf-8", errors="replace")
    return ""


def _gate_reason(gate: dict[str, Any]) -> list[str]:
    checks = gate.get("checks") or {}
    lines = []
    for name in ("diff_scope", "build", "compiled", "patched", "tests", "behavior"):
        c = checks.get(name) or {}
        if c.get("status") not in ("fail", "inconclusive"):
            continue
        if name == "patched":
            stack = _frames(gate.get("patched_report_tail", ""))
            lines.append("the PoC still crashes:\n    " + (stack or c["detail"].split(":", 1)[0]))
        elif name == "tests":
            lines.append("the project's own tests fail with this patch")
        elif name == "behavior":
            lines.append("program output changed on the reproducer (behaviour not preserved)")
        elif name == "compiled":
            lines.append("the edit is not compiled into the binary under test (wrong file?)")
        elif name == "build":
            lines.append("the patch does not compile in the gate's build")
        else:
            lines.append(f"rejected by the edit-scope rules: {c['detail'][:200]}")
    rf = checks.get("refuzz") or {}
    if rf.get("status") == "fail":
        m = _SITE.match(rf.get("detail", ""))
        stack = _frames(_saved_report(gate.get("artifacts") or []))
        lines.append(
            "fuzzing with larger/mutated inputs found a crash in the patched code:\n    "
            + (stack or (m.group("what") if m else "crash"))
        )
    df = checks.get("differential") or {}
    if df.get("status") == "fail":
        lines.append(
            "behaviour changed on an input the unpatched program handled (exit code or output differ)"
        )
    sf = checks.get("safe_fix") or {}
    if sf.get("status") == "fail":
        ev = gate.get("evidence") or {}
        reports = list((ev.get("leak_reports") or {}).values()) + [ev.get("poc_leak_report", "")]
        stack = next((s for s in (_frames(r, "frames") for r in reports) if s), "")
        lines.append(
            "the patch introduces a memory leak:\n    " + (stack or "leak under LeakSanitizer")
        )
    return lines


def summarize(workers: list[dict[str, Any]], max_diff: int = 2500) -> str:
    """One section per distinct round-1 candidate: what it changed and why it was not verified."""
    out, seen = [], set()
    for w in workers:
        key = w.get("diff") or f"{w['hypothesis_id']}{w['worker_index']}"
        if key in seen:
            continue
        seen.add(key)
        verdict = w.get("verdict", "?")
        if w.get("gate"):
            reasons = _gate_reason(w["gate"]) or [f"not verified ({verdict})"]
        elif verdict == "build_failed":
            log = (w.get("build") or {}).get("log_tail", "")
            errs = [ln for ln in log.splitlines() if "error" in ln.lower()][:8]
            reasons = ["does not compile:\n    " + "\n    ".join(errs or [log[-600:]])]
        else:
            reasons = [f"no applicable edit was produced ({(w.get('error') or verdict)[:200]})"]
        part = f"### Attempt {w['hypothesis_id']}·w{w['worker_index']}: {verdict}\n"
        part += "".join(f"- {r}\n" for r in reasons)
        if w.get("diff"):
            part += f"Its diff:\n```diff\n{w['diff'][:max_diff]}\n```\n"
        out.append(part)
    return "\n".join(out)


def hot_files(finding: dict[str, Any], sources: dict[str, str], n: int = 2) -> list[str]:
    """The files of the top `n` in-project frames (crash stack first), in order, visible ones."""
    files: list[str] = []
    for key in ("frames", "alloc_stack", "free_stack"):
        for fr in finding.get(key) or []:
            path = fr.get("file")
            hit = next((p for p in sources if path and (p == path or p.endswith(path))), None)
            if hit and hit not in files:
                files.append(hit)
            if len(files) >= n:
                return files
    return files
