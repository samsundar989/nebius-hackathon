"""Repair-round feedback (D-0059): kind + stack only, never the crashing input or corpus."""

from pathlib import Path

from leakproof.feedback import hot_files, summarize

FUZZ_LOG = """==7==ERROR: AddressSanitizer: stack-buffer-overflow on address 0x7f at pc 0x1 bp 0x2 sp 0x3
WRITE of size 1 at 0x7f thread T0
    #0 0x5dfc3c in decToString /src/jq/src/decNumber/decNumber.c:3724:34
    #1 0x5df1a6 in decNumberToString /src/jq/src/decNumber/decNumber.c:449:3
    #2 0x570d37 in jvp_literal_number_literal /src/jq/src/jv.c:646:5
SUMMARY: AddressSanitizer: stack-buffer-overflow
MS: 2 ChangeByte-InsertRepeatedBytes-; base unit: 0
0x2d,0x31,0x36,0x31,0x36,
-16161616SECRETINPUT
artifact_prefix='/tmp/lp/art/'; Test unit written to /tmp/lp/art/crash-abc
Base64: LTE2MTYxNlNFQ1JFVElOUFVU
"""


def test_refuzz_failure_passes_kind_and_frames_not_the_input(tmp_path: Path) -> None:
    log = tmp_path / "H3_w2_fuzzing_crash-abc.log"
    log.write_text(FUZZ_LOG)
    (tmp_path / "H3_w2_fuzzing_crash-abc.bin").write_bytes(b"-16161616SECRETINPUT")
    worker = {
        "hypothesis_id": "H3",
        "worker_index": 2,
        "verdict": "rejected:refuzz_new_crash",
        "diff": "-int len = digits + 14;\n+char buffer[64];\n",
        "gate": {
            "checks": {
                "patched": {"status": "pass", "detail": "no sanitizer report"},
                "refuzz": {
                    "status": "fail",
                    "detail": "stack-buffer-overflow at decToString /src/jq/src/decNumber/decNumber.c "
                    "from fuzzing:crash-abc (20 bytes); baseline is clean on this input",
                },
            },
            "artifacts": [str(log.with_suffix(".bin")), str(log)],
        },
    }
    text = summarize([worker])
    assert "stack-buffer-overflow" in text and "decToString" in text and "jv.c:646" in text
    for leaked in ("SECRETINPUT", "LTE2MTYx", "0x2d,0x31", "crash-abc", "baseline"):
        assert leaked not in text


def test_tests_and_differential_failures_carry_no_test_output_or_input() -> None:
    worker = {
        "hypothesis_id": "H1",
        "worker_index": 0,
        "verdict": "silenced_only",
        "diff": "+x\n",
        "gate": {
            "checks": {
                "tests": {"status": "fail", "detail": "FAIL: tests/jqtest expected 1.0000000001"},
                "differential": {"status": "fail", "detail": "behaviour changed on 5ab3: rc 0->1"},
            }
        },
    }
    text = summarize([worker])
    assert "tests fail" in text and "behaviour changed" in text
    assert "jqtest" not in text and "5ab3" not in text


def test_hot_files_follow_the_crash_stack() -> None:
    finding = {"frames": [{"file": "/src/a/x.c"}, {"file": "/src/a/y.c"}, {"file": "/src/a/z.c"}]}
    sources = {"/src/a/z.c": "", "/src/a/y.c": "", "/src/a/x.c": ""}
    assert hot_files(finding, sources) == ["/src/a/x.c", "/src/a/y.c"]
