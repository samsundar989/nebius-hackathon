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
