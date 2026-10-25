from leakproof.evidence import explain, strength

PASS = {"status": "pass", "detail": ""}


def test_no_tests_and_silent_harness_is_weak() -> None:
    ev = strength(
        {
            "tests": {"status": "skipped", "detail": ""},
            "refuzz": {"status": "pass", "detail": "rc=0 runs=3054415"},
        },
        {"clean_inputs": 190, "stdout_distinct": 0},
    )
    assert ev["level"] == "weak" and ev["label"] == "verified, needs human review"
    assert ev["refuzz_runs"] == 3054415
    assert "prints nothing" in explain(ev)


def test_tests_plus_varying_output_is_strong() -> None:
    ev = strength({"tests": PASS}, {"clean_inputs": 50, "stdout_distinct": 12})
    assert ev["level"] == "strong" and ev["label"] == "verified"


def test_one_signal_is_medium_and_behavior_counts_as_output() -> None:
    assert strength({"tests": PASS}, {"clean_inputs": 9, "stdout_distinct": 1})["level"] == "medium"
    assert strength({"behavior": PASS}, None)["level"] == "medium"


def test_unmeasured_output_is_reported_as_such() -> None:
    ev = strength({}, None)
    assert ev["output_varies"] is None and ev["level"] == "weak"
    assert "not measured" in explain(ev)
