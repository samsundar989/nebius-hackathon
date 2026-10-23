"""ARVO reproducer output (captured by scripts/arvo_probe.py) parses to the reproduced kind."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from leakproof.findings import parse_report, primary

ROOT = Path(__file__).resolve().parent.parent
CASES = sorted((ROOT / "cases" / "arvo").glob("[0-9]*.json"))


@pytest.mark.parametrize("case_path", CASES, ids=lambda p: p.stem)
def test_arvo_report(case_path: Path) -> None:
    case = json.loads(case_path.read_text())
    report = (ROOT / "tests" / "fixtures" / "arvo" / f"{case['id']}.log").read_text()
    f = primary(parse_report(report))
    assert f is not None and f.kind == case["finding"]["kind"]
    assert f.location and f.location.startswith(f"/src/{case['project']}/")


def test_ansi_colour_codes_are_stripped() -> None:
    raw = "\x1b[1m\x1b[31m==7==ERROR: AddressSanitizer: heap-buffer-overflow on address 0x1\x1b[1m\x1b[0m\n"
    raw += "READ of size 8 at 0x1 thread T0\n    #0 0x5 in f /src/x/a.c:3:7\n"
    f = primary(parse_report(raw))
    assert f is not None and f.kind == "heap-buffer-overflow" and f.location == "/src/x/a.c:3"
