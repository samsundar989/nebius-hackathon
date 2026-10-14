"""Parse NVIDIA compute-sanitizer output (memcheck, leak-check, racecheck, initcheck).

Every line is prefixed with `========= `. Fixtures in tests/fixtures/ come from real runs on the
RTX 5090 (kickoff 3.7); formats vary slightly between CUDA releases, so matching is tolerant.
"""

from __future__ import annotations

import re

from leakproof.findings.model import Finding, Frame

_PREFIX = re.compile(r"^=========\s?")
_HEADS: list[tuple[re.Pattern[str], str, str | None]] = [
    (re.compile(r"Invalid __(global|shared|local)__ (read|write) of size (\d+)"), "oob", None),
    (re.compile(r"Misaligned (?:Shared or Local Address|address)"), "misaligned-access", "CWE-704"),
    (re.compile(r"Leaked (\d+) bytes at (0x[0-9a-fA-F]+)"), "leak", "CWE-401"),
    (
        re.compile(r"Uninitialized __(global|shared|local)__ memory read of size (\d+)"),
        "uninit",
        "CWE-457",
    ),
    (re.compile(r"(Error|Warning): Race reported between (\w+) access"), "race", "CWE-362"),
    (
        re.compile(
            r"Program hit (cuda\w+Error|\w+) \(error (\d+)\) due to \"(.*)\" on CUDA API call to (\w+)"
        ),
        "cuda-api-error",
        None,
    ),
    (
        re.compile(r"Invalid (?:host|device)? ?pointer|cudaErrorInvalidValue"),
        "invalid-pointer",
        "CWE-763",
    ),
]
_DEVICE_FRAME = re.compile(r"^\s*at (.+?)(?:\+0x[0-9a-fA-F]+)? in (.+?):(\d+)\s*$")
_DEVICE_FRAME_NOLINE = re.compile(r"^\s*at (?:0x[0-9a-fA-F]+ in )?(.+?)(?:\+0x[0-9a-fA-F]+)?\s*$")
_HOST_FRAME = re.compile(
    r"^\s*Host Frame:\s*(?:\[(0x[0-9a-fA-F]+)\]\s*)?(.+?)(?:\s+\[(0x[0-9a-fA-F]+)\])?"
    r"(?:\s+in\s+(.+?))?\s*$"
)
_THREAD = re.compile(r"by thread \((\d+),(\d+),(\d+)\) in block \((\d+),(\d+),(\d+)\)")


def _host_frame(index: int, m: re.Match[str]) -> Frame:
    func, where = m.group(2).strip(), (m.group(4) or "").strip()
    loc = re.match(r"^(.*?):(\d+)$", where)
    if loc:
        return Frame(index=index, function=func, file=loc.group(1), line=int(loc.group(2)))
    return Frame(index=index, function=func, module=where or None, pc=m.group(1) or m.group(3))


def parse_compute_sanitizer(text: str) -> list[Finding]:
    raw_lines = text.splitlines()
    lines = [_PREFIX.sub("", ln) if ln.startswith("=========") else None for ln in raw_lines]
    findings: list[Finding] = []
    current: Finding | None = None
    host_section = False
    for raw, line in zip(raw_lines, lines, strict=True):
        if line is None:
            continue
        stripped = line.strip()
        if stripped.startswith(
            ("ERROR SUMMARY", "LEAK SUMMARY", "RACECHECK SUMMARY", "COMPUTE-SANITIZER")
        ):
            current = None
            continue
        head = next(((p.search(stripped), k, c) for p, k, c in _HEADS if p.search(stripped)), None)
        if head and not line.startswith((" ", "\t")):
            m, kind, cwe = head
            finding = Finding(tool="compute-sanitizer", kind=kind, cwe_guess=cwe, summary=stripped)
            if kind == "oob":
                finding.access = m.group(2).upper()
                finding.access_size = int(m.group(3))
                finding.cwe_guess = "CWE-787" if finding.access == "WRITE" else "CWE-125"
                finding.kind = f"{m.group(1)}-out-of-bounds"
            elif kind == "leak":
                finding.leaked_bytes = int(m.group(1))
            findings.append(finding)
            current, host_section = finding, False
            current.raw = raw
            continue
        if current is None:
            continue
        current.raw += "\n" + raw
        if "Saved host backtrace" in stripped:
            host_section = True
            continue
        if hm := _HOST_FRAME.match(stripped):
            frame = _host_frame(
                len(current.alloc_stack if current.kind == "leak" else current.frames), hm
            )
            # Leak backtraces are taken at cudaMalloc time: they are the allocation stack.
            (current.alloc_stack if current.kind == "leak" else current.frames).append(frame)
            if current.kind == "leak":
                current.frames = current.alloc_stack
            continue
        if not host_section and (dm := _DEVICE_FRAME.match(stripped)):
            current.frames.insert(
                0, Frame(index=0, function=dm.group(1), file=dm.group(2), line=int(dm.group(3)))
            )
            continue
        if (
            not host_section
            and stripped.startswith("at ")
            and (dm := _DEVICE_FRAME_NOLINE.match(stripped))
        ):
            current.frames.insert(0, Frame(index=0, function=dm.group(1)))
    for f in findings:
        for i, frame in enumerate(f.frames):
            frame.index = i
    return findings
