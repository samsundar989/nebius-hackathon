from leakproof.gate import compare_tests
from leakproof.gate import test_results as parse_results

CUNIT = """Suite: Persist read
  Test: Empty file ...passed
  Test: v6 client message+props ...FAILED
    1. persist_read_test.c:710  - CU_ASSERT_PTR_NOT_NULL(context->msgs_out.inflight)
Suite: UTF-8
  Test: Empty file ...passed
"""


def test_cunit_results_are_keyed_by_suite() -> None:
    r = parse_results(CUNIT)
    assert r == {
        "Persist read/Empty file": True,
        "Persist read/v6 client message+props": False,
        "UTF-8/Empty file": True,
    }


def test_automake_results() -> None:
    r = parse_results("PASS: tests/jqtest\nFAIL: tests/shtest\nXFAIL: tests/x\n")
    assert r == {"tests/jqtest": True, "tests/shtest": False, "tests/x": True}


def test_baseline_failure_does_not_fail_the_patch() -> None:
    base = parse_results(CUNIT)
    assert compare_tests(base, dict(base)).status == "pass"


def test_newly_failing_or_missing_test_fails() -> None:
    base = parse_results(CUNIT)
    broke = dict(base, **{"UTF-8/Empty file": False})
    assert compare_tests(base, broke).status == "fail"
    missing = {k: v for k, v in base.items() if k != "Persist read/Empty file"}
    c = compare_tests(base, missing)
    assert c.status == "fail" and "did not run (1)" in c.detail


def test_test_names_with_spaces_stay_distinct() -> None:
    r = parse_results("PASS: patch create file\nFAIL: patch dry run doesn't create file\n")
    assert r == {"patch create file": True, "patch dry run doesn't create file": False}


def test_gtest_results_skip_the_summary_repeat() -> None:
    log = "\n".join(
        [
            "[ RUN      ] utSTLImporterExporter.importSTLFile",
            "[       OK ] utSTLImporterExporter.importSTLFile (12 ms)",
            "[ RUN      ] utSTLImporterExporter.exporterTest",
            "[  FAILED  ] utSTLImporterExporter.exporterTest (3 ms)",
            "[  FAILED  ] 1 test, listed below:",
            "[  FAILED  ] utSTLImporterExporter.exporterTest",
        ]
    )
    assert parse_results(log) == {
        "utSTLImporterExporter.importSTLFile": True,
        "utSTLImporterExporter.exporterTest": False,
    }


def test_gtest_lines_pass_the_shell_filter() -> None:
    import re
    import subprocess

    from leakproof.gate import TEST_LINES

    lines = "[       OK ] A.b (1 ms)\n[  FAILED  ] A.c (2 ms)\n[  FAILED  ] A.c\nnoise\n"
    pat = TEST_LINES.strip("'")
    kept = [ln for ln in lines.splitlines() if re.search(pat, ln)]
    assert kept == ["[       OK ] A.b (1 ms)", "[  FAILED  ] A.c (2 ms)"]
    if subprocess.run(["sh", "-c", "command -v grep"], capture_output=True).returncode == 0:
        out = subprocess.run(
            ["sh", "-c", f"grep -E {TEST_LINES}"], input=lines, capture_output=True, text=True
        ).stdout
        assert out.splitlines() == kept
