"""Parse Valgrind memcheck output (leaks, invalid read/write/free)."""

from __future__ import annotations

import re

from leakproof.findings.model import Finding, Frame

_LINE = re.compile(r"^==\d+==\s?(.*)$")
_FRAME = re.compile(r"^(?:at|by) (0x[0-9A-Fa-f]+): (.+?) \((?:(.+?):(\d+)|in (.+?))\)$")
_LEAK = re.compile(
    r"^([\d,]+) (?:\([\d,]+ direct, [\d,]+ indirect\) )?bytes in [\d,]+ blocks are "
    r"(definitely|indirectly|possibly) lost in loss record"
)
_INVALID = re.compile(r"^Invalid (read|write) of size (\d+)")


def _stack(lines: list[str], i: int) -> tuple[list[Frame], int]:
    frames: list[Frame] = []
    while i < len(lines) and (m := _FRAME.match(lines[i].strip())):
        frames.append(
            Frame(
                index=len(frames),
                function=m.group(2),
                file=m.group(3),
                line=int(m.group(4)) if m.group(4) else None,
                module=m.group(5),
                pc=m.group(1),
            )
        )
        i += 1
    return frames, i


def parse_valgrind(text: str) -> list[Finding]:
    lines = [m.group(1) for ln in text.splitlines() if (m := _LINE.match(ln))]
    findings: list[Finding] = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if m := _LEAK.match(line):
            frames, j = _stack(lines, i + 1)
            if m.group(2) in ("definitely", "indirectly"):
                findings.append(
                    Finding(
                        tool="valgrind",
                        kind="leak",
                        cwe_guess="CWE-401",
                        summary=line,
                        frames=frames,
                        alloc_stack=frames,
                        leaked_bytes=int(m.group(1).replace(",", "")),
                        leak_type="direct" if m.group(2) == "definitely" else "indirect",
                        raw="\n".join(lines[i:j]),
                    )
                )
            i = j
            continue
        m = _INVALID.match(line)
        if m or line.startswith(("Invalid free()", "Mismatched free()")):
            frames, j = _stack(lines, i + 1)
            f = Finding(
                tool="valgrind",
                kind="invalid-access",
                cwe_guess="CWE-119",
                summary=line,
                frames=frames,
            )
            if m:
                f.access, f.access_size = m.group(1).upper(), int(m.group(2))
            k = j
            while k < len(lines) and lines[k].strip() and not _INVALID.match(lines[k].strip()):
                text_k = lines[k].strip()
                if "free'd" in text_k or "freed" in text_k:
                    f.free_stack, k = _stack(lines, k + 1)
                    continue
                if "alloc'd" in text_k:
                    f.alloc_stack, k = _stack(lines, k + 1)
                    continue
                k += 1
            if line.startswith("Invalid free()"):
                f.kind, f.cwe_guess = (
                    ("double-free", "CWE-415") if f.free_stack else ("invalid-free", "CWE-590")
                )
            elif line.startswith("Mismatched free()"):
                f.kind, f.cwe_guess = "alloc-dealloc-mismatch", "CWE-762"
            elif f.free_stack:
                f.kind, f.cwe_guess = "use-after-free", "CWE-416"
            elif f.alloc_stack:
                f.kind = "heap-buffer-overflow"
                f.cwe_guess = "CWE-787" if f.access == "WRITE" else "CWE-125"
            f.raw = "\n".join(lines[i:k])
            findings.append(f)
            i = k
            continue
        i += 1
    return findings
