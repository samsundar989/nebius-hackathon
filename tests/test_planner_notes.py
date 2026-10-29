from leakproof.planner import build_messages

FINDING = {"tool": "asan", "kind": "memory-leak", "summary": "leak in f", "frames": []}


def test_notes_reach_the_planner_prompt():
    msgs = build_messages(FINDING, [], ["a.cpp"], "make", notes="free on the EOF path")
    assert "## Reviewer notes on earlier runs\nfree on the EOF path" in msgs[1]["content"]


def test_no_notes_no_section():
    msgs = build_messages(FINDING, [], ["a.cpp"], "make")
    assert "Reviewer notes" not in msgs[1]["content"]
