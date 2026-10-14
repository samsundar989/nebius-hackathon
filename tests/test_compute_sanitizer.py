"""compute-sanitizer parsing on real runs: Kaggle T4 (CUDA 12.8, sanitizer 2025.1) and the
local RTX 5090 under WSL2, where the tool cannot attach."""

from __future__ import annotations

from pathlib import Path

from leakproof.findings import compute_sanitizer_tool_errors, parse_report, primary

FIX = Path(__file__).parent / "fixtures"


def test_wsl2_unsupported_run_has_no_findings_but_tool_errors() -> None:
    text = (FIX / "compute_sanitizer_wsl2_sm120_unsupported.log").read_text()
    assert parse_report(text) == []
    errors = compute_sanitizer_tool_errors(text)
    assert any("WDDM debugger interface" in e for e in errors)
    assert any("Device not supported" in e for e in errors)


def test_clean_run_has_no_tool_errors() -> None:
    text = "========= COMPUTE-SANITIZER\n========= ERROR SUMMARY: 0 errors\n"
    assert compute_sanitizer_tool_errors(text) == []


def test_t4_memcheck_global_oob_write() -> None:
    text = (FIX / "compute_sanitizer_t4_memcheck_oob.log").read_text()
    findings = parse_report(text)
    assert [f.kind for f in findings] == [
        "global-out-of-bounds",
        "cuda-api-error",
        "cuda-api-error",
    ]
    oob = primary(findings)
    assert oob is not None and oob.kind == "global-out-of-bounds"
    assert (oob.cwe_guess, oob.access, oob.access_size) == ("CWE-787", "WRITE", 4)
    assert [(f.function, f.file, f.line) for f in oob.frames] == [
        ("shift_write(int *, int)", "oob_global.cu", 8),
        ("main", "oob_global.cu", 15),
    ]
    assert compute_sanitizer_tool_errors(text) == []


def test_t4_leak_check_allocation_stack() -> None:
    text = (FIX / "compute_sanitizer_t4_leakcheck.log").read_text()
    (leak,) = parse_report(text)
    assert (leak.kind, leak.cwe_guess, leak.leaked_bytes) == ("leak", "CWE-401", 4096)
    sites = [(f.function, f.file, f.line) for f in leak.alloc_stack if f.file]
    assert ("make_buffer(int)", "leak_cudamalloc.cu", 12) in sites
    assert sites[-1] == ("main", "leak_cudamalloc.cu", 19)
    assert compute_sanitizer_tool_errors(text) == []
