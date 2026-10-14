"""Apply LLM-written unified diffs tolerantly.

Models get the *edit* right more often than the diff *syntax*: hunk headers are wrong and context
lines are misquoted (measured on Nemotron 3.5 Lightning, E0). Strategy per hunk:
1. exact match of the hunk's old block (context + removed lines), whitespace-insensitive;
2. else a unique whitespace-insensitive match of just the removed lines (pure insertions need
   step 1).
Ambiguous or missing matches fail loudly. Whatever applies is still judged by the gate.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


class PatchError(ValueError):
    pass


@dataclass
class Hunk:
    lines: list[tuple[str, str]] = field(default_factory=list)  # (op, text) op in " ", "-", "+"

    @property
    def old(self) -> list[str]:
        return [t for op, t in self.lines if op in " -"]

    @property
    def new(self) -> list[str]:
        return [t for op, t in self.lines if op in " +"]

    @property
    def removed_run(self) -> tuple[int, int] | None:
        """(start, end) of the hunk's single contiguous run of '-' lines, if it has exactly one."""
        idx = [i for i, (op, _) in enumerate(self.lines) if op == "-"]
        if not idx or idx[-1] - idx[0] + 1 != len(idx):
            return None
        return idx[0], idx[-1] + 1


def parse_diff(diff: str) -> dict[str, list[Hunk]]:
    files: dict[str, list[Hunk]] = {}
    current: list[Hunk] | None = None
    hunk: Hunk | None = None
    for raw in diff.splitlines():
        if raw.startswith("+++ "):
            name = re.sub(r"^b/", "", raw[4:].split("\t")[0].strip())
            current = files.setdefault(name, [])
            hunk = None
        elif raw.startswith("--- "):
            hunk = None
        elif raw.startswith("@@"):
            if current is None:
                raise PatchError("hunk before file header")
            hunk = Hunk()
            current.append(hunk)
        elif hunk is not None and raw[:1] in (" ", "-", "+"):
            hunk.lines.append((raw[0], raw[1:]))
        elif hunk is not None and raw == "":
            hunk.lines.append((" ", ""))
    if not any(files.values()):
        raise PatchError("no hunks in diff")
    return files


def _norm(line: str) -> str:
    return " ".join(line.split())


def _find(haystack: list[str], needle: list[str]) -> list[int]:
    n = [_norm(x) for x in needle]
    h = [_norm(x) for x in haystack]
    return [i for i in range(len(h) - len(n) + 1) if h[i : i + len(n)] == n]


def apply_hunks(source: str, hunks: list[Hunk]) -> tuple[str, list[str]]:
    """Return (patched source, per-hunk strategy used)."""
    lines = source.splitlines()
    used: list[str] = []
    for hunk in hunks:
        hits = _find(lines, hunk.old) if hunk.old else []
        if len(hits) == 1:
            i = hits[0]
            lines[i : i + len(hunk.old)] = hunk.new
            used.append("exact")
            continue
        run = hunk.removed_run
        if run is None:
            raise PatchError(f"hunk context not found ({len(hits)} matches) and no removed run")
        removed = [t for _, t in hunk.lines[run[0] : run[1]]]
        hits = _find(lines, removed)
        if len(hits) != 1:
            raise PatchError(f"removed lines matched {len(hits)} times")
        # Added lines adjacent to the removed run replace it.
        j = run[1]
        added = []
        while j < len(hunk.lines) and hunk.lines[j][0] == "+":
            added.append(hunk.lines[j][1])
            j += 1
        k = run[0] - 1
        while k >= 0 and hunk.lines[k][0] == "+":
            added.insert(0, hunk.lines[k][1])
            k -= 1
        i = hits[0]
        lines[i : i + len(removed)] = added
        used.append("removed-lines")
    return "\n".join(lines) + ("\n" if source.endswith("\n") else ""), used
