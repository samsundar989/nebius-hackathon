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


def test_same_function_other_line_is_pre_existing() -> None:
    sig = "ERROR:_AddressSanitizer:_heap-buffer-overflow"
    base = _run({"a": ("1", "x", sig)}, {"a": REP})  # unpatched crashes at a.c:3
    pat = _run({"a": ("1", "x", sig)}, {"a": REP})
    assert adv.judge(base, pat, None, TARGET, "/src/p/a.c:3:1")[0] == "adversary_same_bug"
    verdict, _, rows = adv.judge(base, pat, None, TARGET, "/src/p/a.c:9")
    assert verdict == "pass" and rows[0]["outcome"].startswith("pre-existing")


def test_leak_after_unpatched_crash_is_not_attributed() -> None:
    leak = (
        "==1==ERROR: LeakSanitizer: detected memory leaks\n\n"
        "Direct leak of 4 byte(s) in 1 object(s) allocated from:\n"
        "    #0 0x1 in malloc /src/llvm-project/compiler-rt/lib/asan/asan_malloc_linux.cpp:145:3\n"
        "    #1 0x2 in g /src/p/b.c:2:1\n"
    )
    base = _run({"a": ("1", "x", "ERROR:_AddressSanitizer:_SEGV")}, {"a": NEW})
    pat = _run({"a": ("1", "x", "ERROR:_LeakSanitizer:_detected")}, {"a": leak})
    assert adv.judge(base, pat, None, TARGET)[0] == "pass"
    clean = _run({"a": ("0", "x", "")})
    assert adv.judge(clean, pat, None, TARGET)[0] == "adversary_new_crash"


def test_decide_adversary_rejects_only_on_fail() -> None:
    from leakproof.gate import Check, decide

    base = {
        k: Check("pass") for k in ("unpatched_trips", "diff_scope", "build", "compiled", "patched")
    }
    assert decide(base | {"adversary": Check("skipped", "super: no inputs")}) == "verified"
    rej = decide(base | {"adversary": Check("fail", "adversary_same_bug: super: target crash")})
    assert rej == "rejected:adversary_same_bug"


def test_adversary_setting_auto(tmp_path) -> None:  # noqa: ANN001
    from leakproof.cli import adversary_setting

    cfg = tmp_path / "leakproof.toml"
    cfg.write_text('[project]\nname = "x"\nbuild = "make"\nreproduce = "./x"\n')
    assert adversary_setting("auto", str(cfg)) == "super"
    cfg.write_text('[project]\nname = "x"\nbuild = "make"\nreproduce = "./x"\ntest = "make test"\n')
    assert adversary_setting("auto", str(cfg)) == "off"
    cfg.write_text(cfg.read_text() + '[gate]\nadversary = "ultra"\n')
    assert adversary_setting("auto", str(cfg)) == "ultra"
    assert adversary_setting("off", str(cfg)) == "off"
