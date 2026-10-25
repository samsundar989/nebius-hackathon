from leakproof.edits import unified_diff
from leakproof.semantic import change, originals, wide_diff
from leakproof.winner import choose


def test_choose_without_judge_keeps_smallest() -> None:
    assert choose(["bbbb", "a", "cc"], None)[0] == "a"


def test_challenger_needs_both_orders() -> None:
    # A judge that always prefers position B is position-biased: nothing switches.
    biased = lambda a, b: {"prefer": "B", "reason": ""}  # noqa: E731
    win, log = choose(["small", "larger one"], biased)
    assert win == "small" and log[0]["switch"] is False


def test_consistent_preference_switches() -> None:
    def judge(a: str, b: str) -> dict:
        return {"prefer": "A" if a == "larger one" else "B", "reason": ""}

    assert choose(["small", "larger one"], judge)[0] == "larger one"


def test_reverse_apply_rebuilds_original() -> None:
    before = {"/src/p/a.c": "".join(f"line {i}\n" for i in range(80))}
    after = {"/src/p/a.c": before["/src/p/a.c"].replace("line 40\n", "line 40 fixed\nextra\n")}
    after["/src/p/a.c"] = after["/src/p/a.c"].replace("line 3\n", "")
    diff = unified_diff(before, after)
    assert originals(after, diff) == before
    wide = wide_diff(after, diff, context=30)
    assert change(wide) == change(diff) and "line 12" in wide
