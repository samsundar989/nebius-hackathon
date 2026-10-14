"""Every bad-only report captured from the Juliet smoke set must parse (kickoff 3.4: 100%)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from leakproof.findings import parse_report, primary

ROOT = Path(__file__).resolve().parent.parent
CASES = sorted((ROOT / "cases" / "juliet").glob("CWE*.json"))


@pytest.mark.parametrize("case_path", CASES, ids=lambda p: p.stem)
def test_report_parses_to_expected_kind(case_path: Path) -> None:
    case = json.loads(case_path.read_text())
    report = (ROOT / "tests" / "fixtures" / "juliet" / f"{case['id']}.log").read_text()
    if not case["reproducible"]:
        assert case["not_reproducible_reason"], "unexplained miss"
        assert parse_report(report) == []
        return
    finding = primary(parse_report(report))
    assert finding is not None and finding.kind == case["expected_kind"]
    # The first user frame may be a Juliet helper (support/io.c printLine); the test case's own
    # code must appear somewhere in the primary or allocation stack.
    assert finding.location and not finding.location.startswith(("wcsmbs/", "string/"))
    frames = finding.frames + finding.alloc_stack
    assert any(f.file and f.file.startswith("/work/case/") for f in frames)


def test_smoke_set_size() -> None:
    assert len(CASES) == 60
