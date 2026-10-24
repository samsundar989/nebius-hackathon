"""Render a Finding and source windows into prompt text (shared by planner and workers)."""

from __future__ import annotations

from typing import Any

from leakproof.cases.base import Window


def _frame(fr: dict[str, Any]) -> str:
    loc = (
        f"{fr['file']}:{fr['line']}"
        if fr.get("file") and fr.get("line")
        else (fr.get("module") or "?")
    )
    return f"  #{fr['index']} {fr['function']} {loc}"


def _user_frames(frames: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    keep = [fr for fr in frames if fr.get("file") and fr.get("line")]
    return keep[:limit]


def render_finding(f: dict[str, Any], frame_limit: int = 8) -> str:
    lines = [
        f"Sanitizer: {f['tool']}  kind: {f['kind']}  ({f.get('cwe_guess') or 'CWE ?'})",
        f"Summary: {f['summary']}",
    ]
    if f.get("access"):
        lines.append(f"Access: {f['access']} of size {f.get('access_size')}")
    if f.get("leaked_bytes"):
        lines.append(f"Leaked: {f['leaked_bytes']} bytes ({f.get('leak_type')})")
    title = "Allocation stack (leaked object)" if f["kind"] == "leak" else "Crash stack"
    for label, key in (
        (title, "frames"),
        ("Allocated at", "alloc_stack"),
        ("Freed at", "free_stack"),
    ):
        frames = _user_frames(f.get(key) or [], frame_limit)
        if frames:
            lines.append(f"{label} (innermost first):")
            lines += [_frame(fr) for fr in frames]
    return "\n".join(lines)


def render_windows(windows: list[Window], numbered: bool = True) -> str:
    """Each window with its line numbers ("  120| code"), so a worker can address lines by
    number (the `@@ replace ... lines A-B @@` fallback, D-0058)."""
    parts = []
    for w in windows:
        lines = w.text.splitlines()
        marks = "".join(
            f"\n  line {ln} ({why}): {lines[ln - w.start].strip()}"
            for ln, why in sorted(w.marks.items())
            if 0 <= ln - w.start < len(lines)
        )
        body = (
            "\n".join(f"{w.start + k:>5}| {line}" for k, line in enumerate(lines))
            if numbered
            else w.text
        )
        parts.append(
            f"=== {w.path} (lines {w.start}-{w.end}) ==={marks}\n{body}\n=== end {w.path} ==="
        )
    return "\n\n".join(parts)


def shown_ranges(windows: list[Window]) -> dict[str, list[tuple[int, int]]]:
    out: dict[str, list[tuple[int, int]]] = {}
    for w in windows:
        out.setdefault(w.path, []).append((w.start, w.start + len(w.text.splitlines()) - 1))
    return out
