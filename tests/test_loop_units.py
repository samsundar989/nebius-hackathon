"""Fix-loop pieces that need no network or Docker: edits, Juliet hiding, gate logic, worker loop."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from leakproof.cases.base import BuildResult, Window
from leakproof.cases.juliet import CASES_DIR, JULIET, JulietCase
from leakproof.edits import EditError, apply_blocks, parse_blocks, unified_diff
from leakproof.gate import Check, behavior_check, decide, diff_scope, patched_check
from leakproof.worker import run_worker

SRC = "int f(void) {\n    char *p = malloc(4);\n    use(p);\n    return 0;\n}\n"


def block(path: str, search: str, replace: str) -> str:
    return f"{path}\n<<<<<<< SEARCH\n{search}\n=======\n{replace}\n>>>>>>> REPLACE\n"


def test_parse_and_apply_exact() -> None:
    text = "Here:\n```c\n" + block("src/a.c", "    use(p);", "    use(p);\n    free(p);") + "```"
    blocks = parse_blocks(text)
    assert [b.path for b in blocks] == ["src/a.c"]
    out, how = apply_blocks({"/src/proj/src/a.c": SRC}, blocks)
    assert "free(p);" in out["/src/proj/src/a.c"] and how == ["exact"]
    diff = unified_diff({"/src/proj/src/a.c": SRC}, out)
    assert diff.startswith("--- a/src/proj/src/a.c") and "+    free(p);" in diff


def test_whitespace_fallback_and_errors() -> None:
    search, replace = "  use(p);\n\treturn 0;", "  use(p); free(p);\n  return 0;"
    blocks = parse_blocks(block("a.c", search, replace))
    out, how = apply_blocks({"a.c": SRC}, blocks)
    assert how == ["whitespace"] and "free(p);" in out["a.c"]
    with pytest.raises(EditError, match="matches 0 times"):
        apply_blocks({"a.c": SRC}, parse_blocks(block("a.c", "nope();", "x();")))
    with pytest.raises(EditError, match="not one of the files"):
        apply_blocks({"a.c": SRC}, parse_blocks(block("b.c", "use(p);", "x();")))


@pytest.mark.skipif(not JULIET.exists(), reason="Juliet cache not present")
def test_juliet_hides_good_and_main_and_restores() -> None:
    case = JulietCase.load("CWE401_Memory_Leak__char_malloc_05")
    (name,) = case.source_files()
    vis = case.visible_sources()[name]
    assert "OMITGOOD" not in vis and "INCLUDEMAIN" not in vis and "good" not in vis.split("bad")[0]
    assert case.restore(name, vis) == case.original(name)
    with pytest.raises(ValueError):
        case.restore(name, vis.replace("good-path code omitted", "gone"))


@pytest.mark.skipif(not CASES_DIR.exists(), reason="no case files")
def test_juliet_windows_mark_frames() -> None:
    case = JulietCase.load("CWE401_Memory_Leak__char_malloc_05")
    if not JULIET.exists():
        pytest.skip("Juliet cache not present")
    (w,) = case.windows()
    assert 37 in w.marks


def test_diff_scope_rules() -> None:
    ok = "--- a/x\n+++ b/x\n-    use(p);\n+    use(p);\n+    free(p);\n"
    assert diff_scope(ok, ["a.c"], {"a.c"}, None, "add_free", "leak").status == "pass"
    assert diff_scope(ok, ["b.c"], {"a.c"}, None, "add_free", "leak").status == "fail"
    bypass = "--- a/x\n+++ b/x\n+    exit(0);\n"
    assert "exit_bypass" in diff_scope(bypass, ["a.c"], {"a.c"}, None, "other", "leak").detail
    attr = "--- a/x\n+++ b/x\n+__attribute__((no_sanitize(\"address\")))\n"
    assert "sanitizer" in diff_scope(attr, ["a.c"], {"a.c"}, None, "other", "leak").detail
    drop = "--- a/x\n+++ b/x\n-    free(p);\n"
    assert "removed_free" in diff_scope(drop, ["a.c"], {"a.c"}, None, "lifetime_fix", "use-after-free").detail
    assert diff_scope(drop, ["a.c"], {"a.c"}, None, "remove_free", "use-after-free").status == "pass"
    assert diff_scope(drop, ["a.c"], {"a.c"}, None, "other", "double-free").status == "pass"
    root = "/src/jq/"
    assert diff_scope(ok, ["/src/jq/src/jv.c"], None, root, "other", "x").status == "pass"
    for bad in ("/src/jq/tests/t.c", "/src/jq/configure.ac", "/src/other/a.c", "/src/jq/fuzz/f.c"):
        assert diff_scope(ok, [bad], None, root, "other", "x").status == "fail", bad


ASAN = (
    "==1==ERROR: AddressSanitizer: heap-use-after-free on address 0x1 at pc 0x2\n"
    "READ of size 4 at 0x1 thread T0\n    #0 0x5 in f /src/x/a.c:3:7\n"
)


def test_patched_check() -> None:
    assert patched_check(0, False, "", "use-after-free").status == "pass"
    assert patched_check(1, False, ASAN, "use-after-free").detail.startswith("still_crashes")
    assert patched_check(1, False, ASAN, "heap-buffer-overflow").detail.startswith("new_use-after-free")
    assert patched_check(1, False, "Segmentation fault", "x").status == "inconclusive"
    assert patched_check(124, True, "", "x").status == "inconclusive"


def test_decide() -> None:
    p = Check("pass")
    base = {"unpatched_trips": p, "diff_scope": p, "build": p, "patched": p}
    assert decide({**base, "tests": p, "behavior": p}) == "verified"
    assert decide({**base, "tests": Check("skipped")}) == "verified"
    assert decide({**base, "tests": Check("fail")}) == "silenced_only"
    assert decide({**base, "behavior": Check("fail")}) == "silenced_only"
    assert decide({**base, "patched": Check("fail", "still_crashes: x")}) == "rejected:still_crashes"
    assert decide({**base, "patched": Check("inconclusive", "timeout")}) == "inconclusive:timeout"
    assert decide({**base, "build": Check("fail")}) == "build_failed"
    assert decide({**base, "diff_scope": Check("fail")}) == "rejected:diff_scope"
    assert decide({**base, "unpatched_trips": Check("fail")}).startswith("inconclusive")


def test_behavior_check() -> None:
    assert behavior_check("CWE-401", "a\nb\n", "a\nb\n").status == "pass"
    assert behavior_check("CWE-401", "a\nb\n", "a\n").status == "fail"
    assert behavior_check("CWE-416", "a\n", "a\nb\n").status == "pass"
    assert behavior_check("CWE-416", "a\n", "").status == "fail"


class FakeClient:
    """Replays canned replies; records whether thinking was on."""

    def __init__(self, replies: list[str]) -> None:
        self.replies, self.calls = list(replies), []

    def chat(self, model, messages, *, purpose, thinking, **kw):  # noqa: ANN001, ANN201
        self.calls.append((purpose, thinking, messages[-1]["content"]))
        return SimpleNamespace(text=self.replies.pop(0), usd=0.001, latency_s=0.1,
                               finish_reason="stop", completion_tokens=10, reasoning_tokens=5)


FINDING = {"tool": "lsan", "kind": "leak", "cwe_guess": "CWE-401", "summary": "leak",
           "frames": [], "alloc_stack": [], "free_stack": []}
HYP = {"id": "H1", "summary": "free p", "files": ["a.c"], "strategy": "add_free", "risk": "low"}


def _run(client: FakeClient, builds: list[bool]) -> object:
    results = iter(builds)
    return run_worker(client, index=0, finding=FINDING, root_cause="p leaks", hypothesis=HYP,
                      sources={"a.c": SRC}, windows=[Window("a.c", 1, 5, SRC)],
                      restore=lambda p, t: t,
                      build=lambda files: BuildResult(next(results), "a.c:3: error: x", 0.1))


def test_worker_apply_repair_then_build() -> None:
    good = block("a.c", "    use(p);", "    use(p);\n    free(p);")
    client = FakeClient([block("a.c", "nothing();", "x"), good])
    cand = _run(client, [True])
    assert cand.status == "built" and "+    free(p);" in cand.diff
    assert [c[0] for c in client.calls] == ["worker", "worker:apply_repair"]


def test_worker_empty_reply_retries_without_thinking_and_build_repair() -> None:
    good = block("a.c", "    use(p);", "    use(p);\n    free(p);")
    client = FakeClient(["", good, good])
    cand = _run(client, [False, False])
    assert cand.status == "build_failed"
    assert client.calls[1][:2] == ("worker:retry_no_thinking", False)
    assert client.calls[2][0] == "worker:build_repair" and "does not compile" in client.calls[2][2]
