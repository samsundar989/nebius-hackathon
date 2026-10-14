"""Parse clang/gcc sanitizer output (ASan, LSan, UBSan, MSan; plain or under libFuzzer)."""

from __future__ import annotations

import re

from leakproof.findings.model import Finding, Frame

_FRAME = re.compile(r"^\s*#(\d+)\s+(0x[0-9a-fA-F]+)\s+(?:in\s+)?(.*?)\s*$")
_MODULE = re.compile(r"^(.*?)\s*\(([^()]*?)\+0x[0-9a-fA-F]+\)(?:\s*\(BuildId:.*\))?$")
_SRCLOC = re.compile(r"^(.*)\s+(\S+?):(\d+)(?::(\d+))?$")

_ASAN_ERROR = re.compile(r"==\d+==ERROR: AddressSanitizer: (.+)$")
_LSAN_ERROR = re.compile(r"==\d+==ERROR: LeakSanitizer: detected memory leaks")
_MSAN_ERROR = re.compile(r"==\d+==WARNING: MemorySanitizer: (.+)$")
_UBSAN_ERROR = re.compile(r"^(\S+?):(\d+):(\d+): runtime error: (.+)$")
_LEAK_HEAD = re.compile(
    r"^(Direct|Indirect) leak of (\d+) byte\(s\) in (\d+) object\(s\) allocated from:"
)
_ACCESS = re.compile(r"^(READ|WRITE) of size (\d+) at")
_SEGV_ACCESS = re.compile(r"The signal is caused by a (READ|WRITE) memory access")

# ASan bug type -> (kind, CWE). Order matters: first matching prefix wins.
_ASAN_KINDS: list[tuple[str, str, str | None]] = [
    ("heap-use-after-free", "use-after-free", "CWE-416"),
    ("attempting double-free", "double-free", "CWE-415"),
    ("attempting free on address which was not malloc", "invalid-free", "CWE-590"),
    ("alloc-dealloc-mismatch", "alloc-dealloc-mismatch", "CWE-762"),
    ("new-delete-type-mismatch", "alloc-dealloc-mismatch", "CWE-762"),
    ("heap-buffer-overflow", "heap-buffer-overflow", "CWE-122"),
    ("stack-buffer-overflow", "stack-buffer-overflow", "CWE-121"),
    ("dynamic-stack-buffer-overflow", "stack-buffer-overflow", "CWE-121"),
    ("stack-buffer-underflow", "stack-buffer-underflow", "CWE-124"),
    ("global-buffer-overflow", "global-buffer-overflow", "CWE-787"),
    ("stack-use-after-return", "stack-use-after-return", "CWE-562"),
    ("stack-use-after-scope", "stack-use-after-scope", "CWE-416"),
    ("container-overflow", "container-overflow", "CWE-119"),
    ("memcpy-param-overlap", "memcpy-param-overlap", "CWE-475"),
    ("negative-size-param", "negative-size-param", "CWE-195"),
    ("calloc-overflow", "allocation-size-overflow", "CWE-190"),
    ("allocation-size-too-big", "allocation-size-too-big", "CWE-789"),
    ("requested allocation size", "allocation-size-too-big", "CWE-789"),
    ("out-of-memory", "out-of-memory", "CWE-789"),
    ("initialization-order-fiasco", "init-order-fiasco", "CWE-665"),
    ("dynamic-stack-buffer-overflow", "stack-buffer-overflow", "CWE-121"),
    ("unknown-crash", "unknown-crash", "CWE-119"),
    ("stack-overflow", "stack-exhaustion", "CWE-674"),
    ("SEGV", "segv", "CWE-119"),
    ("BUS", "segv", "CWE-119"),
    ("FPE", "div-by-zero", "CWE-369"),
    ("ABRT", "abort", None),
]

_UBSAN_KINDS: list[tuple[str, str, str | None]] = [
    (r"signed integer overflow", "integer-overflow", "CWE-190"),
    (r"unsigned integer overflow", "integer-overflow", "CWE-190"),
    (r"negation of", "integer-overflow", "CWE-190"),
    (r"with insufficient space for an object of type", "object-size-overflow", "CWE-787"),
    (r"null pointer|nullptr", "null-deref", "CWE-476"),
    (
        r"applying (non-zero )?offset .* to null pointer|pointer overflow",
        "pointer-overflow",
        "CWE-119",
    ),
    (r"shift exponent|left shift of", "invalid-shift", "CWE-1335"),
    (r"index .* out of bounds", "index-out-of-bounds", "CWE-129"),
    (r"division by zero", "div-by-zero", "CWE-369"),
    (r"misaligned address", "misaligned-access", "CWE-704"),
    (r"not a valid value for type", "invalid-value", "CWE-704"),
    (r"is outside the range of representable values", "float-cast-overflow", "CWE-681"),
    (r"implicit conversion", "implicit-conversion", "CWE-681"),
    (r"execution reached an unreachable program point", "unreachable", "CWE-670"),
    (
        r"call to function .* through pointer to incorrect function type",
        "bad-function-cast",
        "CWE-686",
    ),
]


def parse_frame(line: str) -> Frame | None:
    m = _FRAME.match(line)
    if not m:
        return None
    index, pc, rest = int(m.group(1)), m.group(2), m.group(3)
    mod = _MODULE.match(rest)
    if mod:
        func = mod.group(1).strip() or "<unknown>"
        return Frame(index=index, function=func, module=mod.group(2), pc=pc)
    loc = _SRCLOC.match(rest)
    if loc:
        return Frame(
            index=index,
            function=loc.group(1).strip(),
            file=loc.group(2),
            line=int(loc.group(3)),
            column=int(loc.group(4)) if loc.group(4) else None,
            pc=pc,
        )
    return Frame(index=index, function=rest or "<unknown>", pc=pc)


def _stack(lines: list[str], start: int) -> tuple[list[Frame], int]:
    """Frames starting at `start` (skipping blank lines before the first); returns (frames, next)."""
    i = start
    frames: list[Frame] = []
    while i < len(lines) and not lines[i].strip() and not frames:
        i += 1
    while i < len(lines):
        frame = parse_frame(lines[i])
        if frame is None:
            break
        frames.append(frame)
        i += 1
    return frames, i


def _asan_kind(bug: str, text: str) -> tuple[str, str | None]:
    for prefix, kind, cwe in _ASAN_KINDS:
        if bug.startswith(prefix):
            if kind == "segv":
                addr = re.search(r"on unknown address (0x[0-9a-fA-F]+)", bug)
                if "zero page" in text or (addr and int(addr.group(1), 16) < 0x1000):
                    return "null-deref", "CWE-476"
            if kind == "heap-buffer-overflow" and re.search(r"located \d+ bytes before", text):
                return "heap-buffer-underflow", "CWE-124"
            if kind == "global-buffer-overflow" and re.search(r"^READ of size", text, re.M):
                return kind, "CWE-125"
            return kind, cwe
    return "unknown", None


def _parse_asan(lines: list[str], start: int, bug: str) -> Finding:
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if lines[j].startswith("SUMMARY:") or "==ABORTING" in lines[j]:
            end = j + 1
            break
    block = lines[start:end]
    text = "\n".join(block)
    kind, cwe = _asan_kind(bug, text)
    finding = Finding(tool="asan", kind=kind, cwe_guess=cwe, summary=bug.strip(), raw=text)
    i = 1
    while i < len(block):
        line = block[i].strip()
        m = _ACCESS.match(line) or _SEGV_ACCESS.search(line)
        if m:
            finding.access = m.group(1)
            if m.re is _ACCESS:
                finding.access_size = int(m.group(2))
        if line.startswith("#") and not finding.frames:
            finding.frames, i = _stack(block, i)
            continue
        if re.match(r"^freed by thread \S+ here:", line):
            finding.free_stack, i = _stack(block, i + 1)
            continue
        if re.match(r"^(previously )?allocated by thread \S+ here:", line):
            finding.alloc_stack, i = _stack(block, i + 1)
            continue
        i += 1
    return finding


def _parse_lsan(lines: list[str], start: int) -> list[Finding]:
    findings: list[Finding] = []
    i = start + 1
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("SUMMARY:"):
            break
        m = _LEAK_HEAD.match(line)
        if m:
            frames, j = _stack(lines, i + 1)
            leak_type = m.group(1).lower()
            findings.append(
                Finding(
                    tool="lsan",
                    kind="leak",
                    cwe_guess="CWE-401",
                    summary=line,
                    frames=frames,
                    alloc_stack=frames,
                    leaked_bytes=int(m.group(2)),
                    leak_type=leak_type,
                    raw="\n".join(lines[i:j]),
                )
            )
            i = j
            continue
        i += 1
    return findings


def _parse_ubsan(lines: list[str], start: int, m: re.Match[str]) -> Finding:
    message = m.group(4)
    kind, cwe = "undefined-behavior", None
    for pattern, k, c in _UBSAN_KINDS:
        if re.search(pattern, message):
            kind, cwe = k, c
            break
    frames, end = _stack(lines, start + 1)
    if not frames:
        # No stack trace (print_stacktrace=0): synthesize a frame from the error location.
        frames = [
            Frame(
                index=0,
                function="<unknown>",
                file=m.group(1),
                line=int(m.group(2)),
                column=int(m.group(3)),
            )
        ]
    return Finding(
        tool="ubsan",
        kind=kind,
        cwe_guess=cwe,
        summary=message.strip(),
        frames=frames,
        raw="\n".join(lines[start:end]),
    )


def _parse_msan(lines: list[str], start: int, bug: str) -> Finding:
    frames, end = _stack(lines, start + 1)
    kind, cwe = ("uninit", "CWE-457") if "use-of-uninitialized-value" in bug else ("msan", None)
    finding = Finding(tool="msan", kind=kind, cwe_guess=cwe, summary=bug.strip(), frames=frames)
    i = end
    while i < len(lines) and not lines[i].startswith("SUMMARY:"):
        if "Uninitialized value was created by a heap allocation" in lines[i]:
            finding.alloc_stack, i = _stack(lines, i + 1)
            continue
        i += 1
    finding.raw = "\n".join(lines[start : i + 1])
    return finding


def parse_sanitizer(text: str) -> list[Finding]:
    lines = text.splitlines()
    findings: list[Finding] = []
    for i, line in enumerate(lines):
        if m := _ASAN_ERROR.search(line):
            findings.append(_parse_asan(lines, i, m.group(1)))
        elif _LSAN_ERROR.search(line):
            findings.extend(_parse_lsan(lines, i))
        elif m := _MSAN_ERROR.search(line):
            findings.append(_parse_msan(lines, i, m.group(1)))
        elif m := _UBSAN_ERROR.match(line.strip()):
            findings.append(_parse_ubsan(lines, i, m))
    return findings
