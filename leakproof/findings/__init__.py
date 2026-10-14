"""Sanitizer/valgrind/compute-sanitizer report parsing into canonical Findings."""

import re

from leakproof.findings.compute_sanitizer import (
    compute_sanitizer_tool_errors,
    parse_compute_sanitizer,
)
from leakproof.findings.model import Finding, Frame
from leakproof.findings.sanitizer import parse_sanitizer
from leakproof.findings.valgrind import parse_valgrind

__all__ = [
    "Finding",
    "Frame",
    "compute_sanitizer_tool_errors",
    "parse_compute_sanitizer",
    "parse_report",
    "parse_sanitizer",
    "parse_valgrind",
    "primary",
]

# When one run produces several reports (e.g. UBSan object-size then ASan for the same write),
# the richest tool wins: ASan/LSan carry allocation and free stacks.
_TOOL_RANK = {"asan": 0, "lsan": 0, "compute-sanitizer": 0, "valgrind": 1, "msan": 1, "ubsan": 2}


_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def parse_report(text: str) -> list[Finding]:
    """Parse any supported report format; returns every finding in order of appearance."""
    text = _ANSI.sub("", text)  # OSS-Fuzz/ARVO stored outputs carry colour codes
    if "========= " in text and ("COMPUTE-SANITIZER" in text or "ERROR SUMMARY" in text):
        return parse_compute_sanitizer(text)
    if "Memcheck, a memory error detector" in text:
        return parse_valgrind(text)
    return parse_sanitizer(text)


def primary(findings: list[Finding]) -> Finding | None:
    """The finding to act on: best tool first, then first reported."""
    if not findings:
        return None
    return min(enumerate(findings), key=lambda p: (_TOOL_RANK.get(p[1].tool, 3), p[0]))[1]
