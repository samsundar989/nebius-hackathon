import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import openai
import pytest

from leakproof.llm import client as client_mod
from leakproof.llm.client import LLMClient, PaymentRequired, StructuredOutputError, extract_json
from leakproof.llm.ledger import BudgetExceeded, CostLedger
from leakproof.llm.models import get


def _resp(
    text: str = "hi",
    prompt: int = 1000,
    completion: int = 1000,
    reasoning: int = 0,
    reasoning_text: str | None = None,
) -> SimpleNamespace:
    msg = SimpleNamespace(content=text, tool_calls=None, reasoning_content=reasoning_text)
    usage = SimpleNamespace(
        prompt_tokens=prompt,
        completion_tokens=completion,
        completion_tokens_details=SimpleNamespace(reasoning_tokens=reasoning),
    )
    return SimpleNamespace(
        choices=[SimpleNamespace(message=msg, finish_reason="stop")], usage=usage
    )


def _status_error(code: int, headers: dict[str, str] | None = None) -> openai.APIStatusError:
    request = httpx.Request("POST", "https://example.invalid/v1/chat/completions")
    response = httpx.Response(code, headers=headers or {}, request=request)
    cls = {
        400: openai.BadRequestError,
        402: openai.APIStatusError,
        429: openai.RateLimitError,
    }.get(code, openai.InternalServerError)
    return cls(f"status {code}", response=response, body=None)


class FakeSDK:
    """Mimics `client.chat.completions.with_raw_response.create`."""

    def __init__(self, outcomes: list[Any]) -> None:
        self.outcomes = list(outcomes)
        self.calls: list[dict[str, Any]] = []
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(with_raw_response=SimpleNamespace(create=self._create))
        )

    def _create(self, **kwargs: Any) -> SimpleNamespace:
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return SimpleNamespace(
            parse=lambda: outcome, headers={"x-ratelimit-remaining-requests": "59"}
        )


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEBIUS_API_KEY", "test-key-not-real")
    monkeypatch.setattr(client_mod.time, "sleep", lambda s: None)


def _client(tmp_path: Path, outcomes: list[Any], budget: float = 10.0) -> tuple[LLMClient, FakeSDK]:
    sdk = FakeSDK(outcomes)
    ledger = CostLedger(path=tmp_path / "ledger.jsonl", budget=budget)
    c = LLMClient(ledger=ledger, run_id="t", sdk_client=sdk)
    c.capabilities = {}  # isolate from the measured tf_capabilities.json
    return c, sdk


def test_cost_and_ledger(tmp_path: Path) -> None:
    c, _ = _client(tmp_path, [_resp(prompt=1_000_000, completion=1_000_000)])
    r = c.chat("lightning", [{"role": "user", "content": "x"}], purpose="unit")
    assert r.usd == pytest.approx(0.06 + 0.24)
    rows = [json.loads(line) for line in (tmp_path / "ledger.jsonl").read_text().splitlines()]
    assert rows[0]["model"] == get("lightning").id and rows[0]["usd"] == pytest.approx(0.30)
    assert r.ratelimit_headers == {"x-ratelimit-remaining-requests": "59"}


def test_budget_guard_forces_stop(tmp_path: Path) -> None:
    # Each call costs $0.30 on Lightning; a $0.50 budget allows two calls, then hard-stops.
    big = _resp(prompt=1_000_000, completion=1_000_000)
    c, sdk = _client(tmp_path, [big, big, big], budget=0.50)
    c.chat("lightning", [], purpose="unit")
    c.chat("lightning", [], purpose="unit")
    with pytest.raises(BudgetExceeded):
        c.chat("lightning", [], purpose="unit")
    assert len(sdk.calls) == 2  # the third request was never sent


def test_ledger_cap_counts_whole_file(tmp_path: Path) -> None:
    path = tmp_path / "ledger.jsonl"
    path.write_text(json.dumps({"usd": 4.99}) + "\n")
    ledger = CostLedger(path=path, budget=10.0, ledger_cap=5.0)
    ledger.check()
    path.write_text(path.read_text() + json.dumps({"usd": 0.02}) + "\n")
    with pytest.raises(BudgetExceeded):
        ledger.check()


def test_retries_429_then_succeeds(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    slept: list[float] = []
    monkeypatch.setattr(client_mod.time, "sleep", slept.append)
    c, sdk = _client(tmp_path, [_status_error(429, {"retry-after": "3"}), _resp()])
    r = c.chat("nano", [], purpose="unit")
    assert r.attempts == 2 and slept == [3.0] and len(sdk.calls) == 2


def test_402_is_budget_stop(tmp_path: Path) -> None:
    c, _ = _client(tmp_path, [_status_error(402)])
    with pytest.raises(PaymentRequired):
        c.chat("nano", [], purpose="unit")


def test_reasoning_field_and_thinking_kwargs(tmp_path: Path) -> None:
    c, sdk = _client(tmp_path, [_resp(reasoning=50, reasoning_text="because")])
    c.capabilities = {get("ultra").id: {"thinking_method": "reasoning_effort"}}
    r = c.chat("ultra", [], purpose="unit", thinking=False)
    assert r.reasoning == "because" and r.reasoning_field == "reasoning_content"
    assert sdk.calls[0]["reasoning_effort"] == "none"


def test_structured_repairs_once(tmp_path: Path) -> None:
    schema = {
        "type": "object",
        "properties": {"n": {"type": "integer"}},
        "required": ["n"],
        "additionalProperties": False,
    }
    c, sdk = _client(tmp_path, [_resp('{"n": "two"}'), _resp('```json\n{"n": 2}\n```')])
    value, _ = c.structured("lightning", [{"role": "user", "content": "n?"}], schema, purpose="u")
    assert value == {"n": 2}
    assert "response_format" in sdk.calls[0] and len(sdk.calls) == 2


def test_structured_falls_back_when_response_format_rejected(tmp_path: Path) -> None:
    schema = {"type": "object", "required": ["ok"]}
    c, sdk = _client(tmp_path, [_status_error(400), _resp('{"ok": true}')])
    value, _ = c.structured("nano", [], schema, purpose="u")
    assert value == {"ok": True}
    assert "response_format" not in sdk.calls[1]
    assert c.capabilities[get("nano").id]["json_schema_accepted"] is False


def test_structured_gives_up_after_one_repair(tmp_path: Path) -> None:
    c, _ = _client(tmp_path, [_resp("nope"), _resp("still nope")])
    with pytest.raises(StructuredOutputError):
        c.structured("nano", [], {"type": "object"}, purpose="u", use_response_format=False)


def test_extract_json_with_prose() -> None:
    assert extract_json('Sure! {"a": [1, 2]} done') == {"a": [1, 2]}


def test_structured_falls_back_on_length_runaway(tmp_path: Path) -> None:
    runaway = _resp('{"n": 1.2345678901234567890123')
    runaway.choices[0].finish_reason = "length"
    c, sdk = _client(tmp_path, [runaway, _resp('{"n": 1}')])
    schema = {"type": "object", "properties": {"n": {"type": "number"}}, "required": ["n"]}
    value, _ = c.structured("lightning", [], schema, purpose="u", use_response_format=True)
    assert value == {"n": 1} and "response_format" not in sdk.calls[1]
