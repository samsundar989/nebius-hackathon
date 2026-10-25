from leakproof import gate_cli as gc
from leakproof.gate_fuzz import Row

REPORT = """==1==ERROR: AddressSanitizer: heap-buffer-overflow on address 0x1 at pc 0x2 bp 0x3 sp 0x4
READ of size 1 at 0x1 thread T0
    #0 0x5 in parse /src/p/src/p.c:10:3
    #1 0x6 in main /src/p/src/main.c:5:1
"""
OTHER = REPORT.replace("parse /src/p/src/p.c", "emit /src/p/src/out.c")
SIG = "ERROR:_AddressSanitizer:_heap-buffer-overflow"
TARGET = ("heap-buffer-overflow", "parse /src/p/src/p.c")


def run(rows: dict[str, tuple[str, str, str]], reports: dict[str, str] | None = None) -> gc.Run:
    return gc.Run({n: Row(*v) for n, v in rows.items()}, reports or {})


def test_generate_is_deterministic_and_excludes_the_poc() -> None:
    a, b = gc.generate(b"[1,2,3]\n"), gc.generate(b"[1,2,3]\n")
    assert a == b and len(a) > 150
    assert all(d != b"[1,2,3]\n" for _, d in a)
    assert any(n.startswith("trunc_") for n, _ in a) and any(n.startswith("digits") for n, _ in a)


def test_target_crash_recurring_is_the_same_bug() -> None:
    base = run({"a": ("1", "x", SIG), "b": ("0", "y", "")}, {"a": REPORT})
    patched = run({"a": ("1", "x", SIG), "b": ("0", "y", "")}, {"a": REPORT})
    refuzz, diff = gc.judge(base, patched, TARGET)
    assert refuzz[0] == "fail" and refuzz[1].startswith("same bug")
    assert diff[0] == "pass"


def test_new_signature_fails_and_known_one_is_pre_existing() -> None:
    base = run({"a": ("1", "x", SIG), "b": ("0", "y", "")}, {"a": OTHER})
    pre = gc.judge(base, run({"a": ("1", "x", SIG), "b": ("0", "y", "")}, {"a": OTHER}), TARGET)
    assert pre[0][0] == "pass" and "pre-existing" in pre[0][1]
    new = gc.judge(
        base,
        run({"a": ("0", "x", ""), "b": ("1", "y", SIG)}, {"b": REPORT.replace("parse", "fresh")}),
        TARGET,
    )
    assert new[0][0] == "fail" and new[0][1].startswith("new crash")


def test_behaviour_change_on_a_clean_input() -> None:
    base = run({"a": ("0", "aaaa", ""), "b": ("1", "bbbb", "")})
    refuzz, diff = gc.judge(base, run({"a": ("0", "aaaa", ""), "b": ("0", "bbbb", "")}), TARGET)
    assert refuzz[0] == "pass" and diff[0] == "fail" and "b: exit 1->0" in diff[1]
