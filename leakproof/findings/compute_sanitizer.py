"""Parse NVIDIA compute-sanitizer output (memcheck, leak-check, racecheck, initcheck).

Every line is prefixed with `========= `. Fixtures in tests/fixtures/ come from real runs on the
Kaggle T4 (kickoff 3.7; sanitizer 2025.1); formats vary slightly between CUDA releases, so matching is tolerant.
"""

from __future__ import annotations

import re

from leakproof.findings.model import Finding, Frame

_PREFIX = re.compile(r"^=========\s?")
_HEADS: list[tuple[re.Pattern[str], str, str | None]] = [
    (re.compile(r"Invalid __(global|shared|local)__ (read|write) of size (\d+)"), "oob", None),
    (re.compile(r"Misaligned (?:Shared or Local Address|address)"), "misaligned-access", "CWE-704"),
    (re.compile(r"Leaked ([\d,]+) bytes at (0x[0-9a-fA-F]+)"), "leak", "CWE-401"),
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
# 2025.x layout: "Host Frame: main in oob_global.cu:15 [0x8c3d] in oob_global" or
# "Host Frame: cudaMalloc [0x52b25] in leak_cudamalloc" (no source line).
_HOST_FRAME_NEW = re.compile(
    r"^\s*Host Frame:\s*(?P<func>.+?)(?: in (?P<file>[^\s\[]+):(?P<line>\d+))?"
    r" \[(?P<pc>0x[0-9a-fA-F]+)\] in (?P<module>\S+)\s*$"
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
                finding.leaked_bytes = int(m.group(1).replace(",", ""))
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
        if (nm := _HOST_FRAME_NEW.match(stripped)) or (hm := _HOST_FRAME.match(stripped)):
            index = len(current.alloc_stack if current.kind == "leak" else current.frames)
            if nm:
                frame = Frame(
                    index=index,
                    function=nm["func"].strip(),
                    file=nm["file"],
                    line=int(nm["line"]) if nm["line"] else None,
                    module=nm["module"],
                    pc=nm["pc"],
                )
            else:
                frame = _host_frame(index, hm)
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


_TOOL_ERRORS = re.compile(
    r"Failed to initialize|Device not supported|Unable to|could not be loaded|"
    r"process didn't terminate successfully|Target application returned an error"
)


def compute_sanitizer_tool_errors(text: str) -> list[str]:
    """Lines where compute-sanitizer itself failed (no instrumentation, crashed target).

    A run with tool errors and zero findings is NOT clean: on WSL2 without the WDDM debugger
    interface, or on a GPU the release does not support, the kernel runs uninstrumented and the
    report has no findings. The gate must treat such runs as inconclusive.
    """
    errors = []
    for raw in text.splitlines():
        if not raw.startswith("========="):
            continue
        line = _PREFIX.sub("", raw).strip()
        if _TOOL_ERRORS.search(line):
            errors.append(line)
    return errors
