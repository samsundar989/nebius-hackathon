from leakproof import adversary as adv
from leakproof import gate_cli as gc
from leakproof import gate_fuzz as gf

TARGET = ("heap-buffer-overflow", "f /src/p/a.c")
REP = "==1==ERROR: AddressSanitizer: heap-buffer-overflow on address\n    #0 0x1 in f /src/p/a.c:3:1\n"
NEW = "==1==ERROR: AddressSanitizer: SEGV on unknown address\n    #0 0x1 in g /src/p/b.c:9:1\n"


def _run(rows: dict[str, tuple[str, str, str]], reports: dict[str, str] | None = None) -> gc.Run:
    return gc.Run({k: gf.Row(*v) for k, v in rows.items()}, reports or {})


def test_same_bug_rejects_unless_reference_has_it() -> None:
    base = _run({"a": ("1", "x", "ERROR:_AddressSanitizer:_heap-buffer-overflow")}, {"a": REP})
    pat = _run({"a": ("1", "x", "ERROR:_AddressSanitizer:_heap-buffer-overflow")}, {"a": REP})
    assert adv.judge(base, pat, None, TARGET)[0] == "adversary_same_bug"
    assert adv.judge(base, pat, pat, TARGET)[0] == "pass"  # the developer's fix has it too


def test_new_crash_and_pre_existing() -> None:
    base = _run({"a": ("0", "x", "")})
    pat = _run({"a": ("1", "x", "ERROR:_AddressSanitizer:_SEGV")}, {"a": NEW})
    assert adv.judge(base, pat, None, TARGET)[0] == "adversary_new_crash"
    base2 = _run({"a": ("1", "x", "ERROR:_AddressSanitizer:_SEGV")}, {"a": NEW})
    assert adv.judge(base2, pat, None, TARGET)[0] == "pass"


def test_behaviour_change_compares_with_reference_when_present() -> None:
    base = _run({"a": ("0", "out1", "")})
    pat = _run({"a": ("0", "out2", "")})
    assert adv.judge(base, pat, None, TARGET)[0] == "behaviour_change"
    assert adv.judge(base, pat, _run({"a": ("0", "out2", "")}), TARGET)[0] == "pass"


def test_decode() -> None:
    hexed = {"encoding": "hex", "prefix": "41", "repeat": "42", "count": 3, "suffix": "0a"}
    assert adv.decode(hexed) == b"ABBB\n"
    assert adv.decode({"encoding": "hex", "prefix": "zz"}) is None
    assert adv.decode({"encoding": "text", "prefix": "a", "repeat": "", "count": 0}) == b"a"
