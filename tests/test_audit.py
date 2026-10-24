"""Check 8 (audit flag): shape of the result; never raises on bad model output."""

from typing import Any

from leakproof.audit import CHECKS, audit
from leakproof.llm.client import StructuredOutputError


class Res:
    model, usd = "nano-test", 0.0001


class FakeClient:
    def __init__(self, value: Any = None, fail: bool = False) -> None:
        self.value, self.fail, self.calls = value, fail, []

    def structured(self, model: str, messages: list, schema: dict, **kw: Any) -> tuple:
        self.calls.append((model, messages, kw))
        if self.fail:
            raise StructuredOutputError("bad")
        return self.value, Res()


def test_audit_collects_flags_and_sees_no_gate_data() -> None:
    value = {k: {"flag": k == "silencing", "note": "n"} for k in CHECKS}
    client = FakeClient(value)
    out = audit(client, {"kind": "heap-buffer-overflow", "location": "a.c:3"}, "-x\n+y\n")
    assert out["flags"] == ["silencing"] and out["model"] == "nano-test"
    model, messages, kw = client.calls[0]
    assert model == "lightning" and kw["thinking"] is False and kw["purpose"] == "audit"
    text = " ".join(m["content"] for m in messages)
    assert "refuzz" not in text and "corpus" not in text and "verdict" not in text


def test_audit_failure_is_recorded_not_raised() -> None:
    out = audit(FakeClient(fail=True), {}, "+y\n")
    assert out["flags"] == [] and "error" in out
