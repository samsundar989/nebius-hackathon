"""Gate v1 checks 5-7: amplification and classification logic (no Docker)."""

from leakproof import gate_fuzz as gf
from leakproof.gate import Check, decide

ASAN_HBO = """==1==ERROR: AddressSanitizer: heap-buffer-overflow on address 0x602 at pc 0x1 bp 0x2 sp 0x3
WRITE of size 1 at 0x602 thread T0
    #0 0x55 in decNumberToString /src/jq/src/decNumber/decNumber.c:3900:5
    #1 0x56 in jv_number_tostring /src/jq/src/jv.c:650:5
"""
ASAN_SBO = ASAN_HBO.replace("heap-buffer-overflow", "stack-buffer-overflow")


def test_amplify_is_generic_and_deterministic() -> None:
    poc = b'[1,{"a":123456789e5}]'
    out = dict(gf.amplify(poc))
    assert out == dict(gf.amplify(poc))
    assert out["digits_x8"] == b'[1,{"a":' + b"123456789" * 8 + b"e5}]"
    assert out["whole_x2"] == poc * 2
    assert out["last_elem_x2"] == b'[1,{"a":123456789e5},{"a":123456789e5}]'
    assert poc not in out.values()
    assert len(set(out.values())) == len(out)


def test_amplify_grows_every_digit_run_not_only_the_longest() -> None:
    # jq 42530604's PoC: the exponent is the longest run; the mantissa is what overflows.
    out = dict(gf.amplify(b"        -16E-1061947065"))
    assert out["digits_x2"] == b"        -16E-10619470651061947065"
    assert out["digits1_x8"] == b"        -" + b"16" * 8 + b"E-1061947065"


def test_amplify_binary_input_without_runs() -> None:
    out = dict(gf.amplify(b"\x00\x01\x02"))
    assert "digits_x2" not in out and "alpha_x2" not in out
    assert out["whole_x8"] == b"\x00\x01\x02" * 8


def test_amplify_line_input_duplicates_last_line() -> None:
    out = dict(gf.amplify(b"GET /\nHost: x\n"))
    assert out["last_elem_x2"] == b"GET /\nHost: x\nHost: x\n"


def test_differential_flags_new_crash_and_behaviour_change() -> None:
    base = gf.parse_rows("a 0 aaa \nb 0 bbb \nc 1 ccc ERROR:_AddressSanitizer:_heap-use-after-free")
    same = gf.parse_rows("a 0 aaa \nb 0 bbb \nc 0 ccc ")
    assert gf.differential(base, same)[0] == "pass"
    crash = gf.parse_rows("a 1 aaa ERROR:_AddressSanitizer:_SEGV\nb 0 bbb \nc 0 ccc ")
    assert gf.differential(base, crash)[0] == "fail"
    changed = gf.parse_rows("a 0 zzz \nb 0 bbb \nc 0 ccc ")
    st, detail = gf.differential(base, changed)
    assert st == "fail" and "stdout" in detail
    assert gf.differential({}, same)[0] == "skipped"


def test_safe_fix_only_counts_new_memory_safety_kinds() -> None:
    base = gf.parse_rows("a 0 x \nb 1 x ERROR:_LeakSanitizer:_detected")
    assert gf.safe_fix(base, base)[0] == "pass"
    leak = gf.parse_rows(
        "a 1 x ERROR:_LeakSanitizer:_detected\nb 1 x ERROR:_LeakSanitizer:_detected"
    )
    assert gf.safe_fix(base, leak)[0] == "fail"
    timeout = gf.parse_rows("a 1 x ERROR:_libFuzzer:_timeout\nb 0 x ")
    assert gf.safe_fix(base, timeout)[0] == "pass"


def test_attribute_pre_existing_bug_elsewhere_is_not_blamed() -> None:
    key = gf.crash_key(ASAN_SBO)
    assert key is not None and key[0] == "stack-buffer-overflow"
    # Baseline is the original heap overflow on the long input: the patch moved it -> blamed.
    assert gf.attribute(key, ASAN_HBO, "/src/jq/src/jv.c:650:5")[0] is True
    # Baseline crashes identically somewhere that is not the target -> pre-existing.
    assert gf.attribute(key, ASAN_SBO, "/src/jq/src/jv.c:999:1")[0] is False
    # Identical crash *at* the target location is still the patch's failure.
    assert gf.attribute(key, ASAN_SBO, key[1])[0] is True
    assert gf.attribute(key, "", "x")[0] is True


def test_crash_key_libfuzzer_timeout() -> None:
    assert gf.crash_key("==7== ERROR: libFuzzer: timeout after 25 seconds") == ("timeout", "")


def test_decide_v1_rejections() -> None:
    base = {
        "unpatched_trips": Check("pass"),
        "diff_scope": Check("pass"),
        "build": Check("pass"),
        "compiled": Check("pass"),
        "patched": Check("pass"),
        "tests": Check("pass"),
    }
    assert decide(base) == "verified"
    assert decide(base | {"refuzz": Check("fail")}) == "rejected:refuzz_new_crash"
    assert decide(base | {"differential": Check("fail")}) == "rejected:differential"
    assert decide(base | {"safe_fix": Check("fail")}) == "rejected:safe_fix"
    assert decide(base | {"refuzz": Check("inconclusive")}) == "inconclusive:refuzz"
    assert decide(base | {"refuzz": Check("skipped")}) == "verified"
