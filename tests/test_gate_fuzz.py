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


def test_safe_fix_masked_leak_is_not_new_and_reference_decides() -> None:
    # mosquitto 42520883: the baseline dies of the invalid free before LSan can run.
    base = gf.parse_rows("a 1 x ERROR:_AddressSanitizer:_attempting\nb 0 x ")
    leak = gf.parse_rows("a 1 x ERROR:_LeakSanitizer:_detected\nb 0 x ")
    st, detail = gf.safe_fix(base, leak)
    assert st == "pass" and "unmasked" in detail
    # With the developer fix as reference: same leak there -> fine; reference clean -> new.
    assert gf.safe_fix(base, leak, ref=leak)[0] == "pass"
    clean = gf.parse_rows("a 0 x \nb 0 x ")
    assert gf.safe_fix(base, leak, ref=clean)[0] == "fail"


def test_diff_scope_defers_removed_free_for_arvo_only() -> None:
    from leakproof.gate import REMOVED_FREE_DEFERRED, diff_scope

    diff = "--- a/x\n+++ b/x\n-        zip_source_free(src_window);\n"
    p = ["/src/libzip/lib/zip_open.c"]
    assert diff_scope(diff, p, None, "/src/libzip/", "other", "use-after-free").status == "fail"
    ok = diff_scope(
        diff, p, None, "/src/libzip/", "other", "use-after-free", defer_removed_free=True
    )
    assert ok.status == "pass" and ok.detail.startswith(REMOVED_FREE_DEFERRED)


def test_crash_key_deadly_signal_takes_first_project_frame() -> None:
    rep = (
        "==476== ERROR: libFuzzer: deadly signal\n"
        "    #7 0x7f in __assert_fail (/lib/x86_64-linux-gnu/libc.so.6+0x33fd5)\n"
        "    #8 0x73f6ca in get_lvalue /src/quickjs/quickjs.c\n"
    )
    assert gf.crash_key(rep) == ("deadly signal", "get_lvalue /src/quickjs/quickjs.c")


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


def test_attribute_with_developer_fix_reference() -> None:
    key = gf.crash_key(ASAN_SBO)
    assert key is not None
    # Baseline differs, but the developer's fix shows the same crash: pre-existing.
    blame, why = gf.attribute(key, ASAN_HBO, "x", reference_report=ASAN_SBO)
    assert blame is False and "developer fix crashes identically" in why
    # Developer fix is clean on it: the patch is blamed.
    blame, why = gf.attribute(key, ASAN_HBO, "x", reference_report="")
    assert blame is True and "developer fix is clean" in why


def test_diff_scope_rejects_harness_files_wherever_they_live() -> None:
    from leakproof.gate import diff_scope

    diff = "--- a/x\n+++ b/x\n-a\n+b\n"
    for path in ("/src/lz4/ossfuzz/f.c", "/src/onig/harnesses/base.c", "/src/h3/apps/fuzzers/f.c"):
        root = "/".join(path.split("/")[:3]) + "/"
        assert diff_scope(diff, [path], None, root, "other", "x").status == "fail"
    pcre = "/src/pcre2/src/pcre2_fuzzsupport.c"
    body = {pcre: "int LLVMFuzzerTestOneInput(const uint8_t *d, size_t n) { return 0; }"}
    st = diff_scope(diff, [pcre], None, "/src/pcre2/", "other", "x", body)
    assert st.status == "fail" and "fuzz_harness_file" in st.detail
    ok = diff_scope(diff, [pcre], None, "/src/pcre2/", "other", "x", {pcre: "int f(void);"})
    assert ok.status == "pass"


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
