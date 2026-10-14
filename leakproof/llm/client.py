"""Thin metered wrapper over the `openai` SDK pointed at Nebius Token Factory.

Every call goes through `_create`, which: checks the budget, retries 429/5xx/529 with backoff
honoring Retry-After, records usage + computed $ in the cost ledger, and returns the response
headers so callers can see `x-ratelimit-*`.

Nemotron quirks handled here (see docs/FEEDBACK.md for measurements):
- reasoning is on by default; `think` maps on/off/effort to whichever request knob the model
  actually honors (`chat_template_kwargs.enable_thinking` or top-level `reasoning_effort`);
- the reasoning text comes back as `reasoning_content` or `reasoning`;
- `response_format: json_schema` may be ignored or rejected, so `structured` always also puts the
  schema in the prompt, validates, and repair-retries once.
"""

from __future__ import annotations

import json
import os
import random
import re
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import jsonschema
import openai

from leakproof.config import TF_BASE_URL, load_dotenv, require
from leakproof.llm.ledger import BudgetExceeded, CostLedger, LedgerEntry
from leakproof.llm.models import ModelSpec, get

RETRY_STATUS = {408, 409, 429, 500, 502, 503, 504, 529}
CAPABILITIES_PATH = Path(__file__).with_name("tf_capabilities.json")
THINKING_METHODS = ("chat_template_kwargs", "reasoning_effort")


class StructuredOutputError(RuntimeError):
    pass


class PaymentRequired(BudgetExceeded):
    """Token Factory returned 402: the account balance is gone."""


@dataclass
class ChatResult:
    model: str
    text: str
    reasoning: str
    reasoning_field: str | None
    prompt_tokens: int
    completion_tokens: int
    reasoning_tokens: int
    usd: float
    latency_s: float
    finish_reason: str | None
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    headers: dict[str, str] = field(default_factory=dict)
    attempts: int = 1

    @property
    def ratelimit_headers(self) -> dict[str, str]:
        return {k: v for k, v in self.headers.items() if k.lower().startswith("x-ratelimit")}


def _load_capabilities() -> dict[str, dict[str, Any]]:
    if CAPABILITIES_PATH.exists():
        return json.loads(CAPABILITIES_PATH.read_text())
    return {}


def thinking_request(method: str, on: bool, effort: str | None = None) -> dict[str, Any]:
    """Request kwargs for one thinking-control method."""
    if method == "chat_template_kwargs":
        return {"extra_body": {"chat_template_kwargs": {"enable_thinking": on}}}
    if method == "reasoning_effort":
        return {"reasoning_effort": (effort or "medium") if on else "none"}
    raise ValueError(f"unknown thinking method {method!r}")


def extract_json(text: str) -> Any:
    """Parse the first JSON object/array in `text`, tolerating code fences and prose around it."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    decoder = json.JSONDecoder()
    for i, ch in enumerate(text):
        if ch in "{[":
            try:
                obj, _ = decoder.raw_decode(text[i:])
                return obj
            except json.JSONDecodeError:
                continue
    raise ValueError("no JSON value found in model output")


class LLMClient:
    def __init__(
        self,
        ledger: CostLedger | None = None,
        run_id: str = "adhoc",
        max_retries: int = 5,
        timeout_s: float = 300.0,
        sdk_client: Any | None = None,
    ) -> None:
        load_dotenv()
        self.ledger = ledger or CostLedger()
        self.run_id = run_id
        self.max_retries = max_retries
        self.capabilities = _load_capabilities()
        self._sdk = sdk_client or openai.OpenAI(
            base_url=os.environ.get("TF_BASE_URL", TF_BASE_URL),
            api_key=require("NEBIUS_API_KEY"),
            max_retries=0,  # retries are ours, so they are visible and metered
            timeout=timeout_s,
        )

    # ------------------------------------------------------------------ core call
    def _create(self, spec: ModelSpec, purpose: str, **kwargs: Any) -> ChatResult:
        self.ledger.check()
        attempt = 0
        while True:
            attempt += 1
            t0 = time.monotonic()
            try:
                raw = self._sdk.chat.completions.with_raw_response.create(model=spec.id, **kwargs)
            except openai.APIStatusError as exc:
                if exc.status_code == 402:
                    raise PaymentRequired(f"Token Factory 402: {exc.message}") from exc
                if exc.status_code in RETRY_STATUS and attempt <= self.max_retries:
                    time.sleep(self._backoff(attempt, exc.response.headers))
                    continue
                raise
            except (openai.APIConnectionError, openai.APITimeoutError):
                if attempt <= self.max_retries:
                    time.sleep(self._backoff(attempt, {}))
                    continue
                raise
            latency = time.monotonic() - t0
            break

        resp = raw.parse()
        headers = {k.lower(): v for k, v in raw.headers.items()}
        result = self._to_result(spec, resp, latency, headers, attempt)
        self.ledger.record(
            LedgerEntry(
                model=spec.id,
                purpose=purpose,
                run_id=self.run_id,
                prompt_tokens=result.prompt_tokens,
                completion_tokens=result.completion_tokens,
                reasoning_tokens=result.reasoning_tokens,
                usd=result.usd,
                latency_s=round(latency, 3),
            )
        )
        return result

    @staticmethod
    def _backoff(attempt: int, headers: Mapping[str, str]) -> float:
        retry_after = headers.get("retry-after") or headers.get("Retry-After")
        if retry_after:
            try:
                return min(float(retry_after), 120.0)
            except ValueError:
                pass
        return min(2 ** (attempt - 1), 60) + random.uniform(0, 0.5)

    @staticmethod
    def _to_result(
        spec: ModelSpec, resp: Any, latency: float, headers: dict[str, str], attempts: int
    ) -> ChatResult:
        choice = resp.choices[0]
        msg = choice.message
        reasoning, reasoning_field = "", None
        for name in ("reasoning_content", "reasoning"):
            value = getattr(msg, name, None)
            if value is None and getattr(msg, "model_extra", None):
                value = msg.model_extra.get(name)
            if value:
                reasoning, reasoning_field = value, name
                break
        usage = resp.usage
        prompt = getattr(usage, "prompt_tokens", 0) or 0
        completion = getattr(usage, "completion_tokens", 0) or 0
        details = getattr(usage, "completion_tokens_details", None)
        reasoning_tokens = (getattr(details, "reasoning_tokens", 0) or 0) if details else 0
        # OpenAI convention: reasoning tokens are a subset of completion tokens. If a backend
        # reports them separately (reasoning > completion), bill both rather than undercount.
        billable_out = completion + (reasoning_tokens if reasoning_tokens > completion else 0)
        tool_calls = [
            {"id": tc.id, "name": tc.function.name, "arguments": tc.function.arguments}
            for tc in (msg.tool_calls or [])
        ]
        return ChatResult(
            model=spec.id,
            text=msg.content or "",
            reasoning=reasoning,
            reasoning_field=reasoning_field,
            prompt_tokens=prompt,
            completion_tokens=completion,
            reasoning_tokens=reasoning_tokens,
            usd=spec.cost(prompt, billable_out),
            latency_s=latency,
            finish_reason=choice.finish_reason,
            tool_calls=tool_calls,
            headers=headers,
            attempts=attempts,
        )

    # ------------------------------------------------------------------ public helpers
    def think(self, model: str, on: bool, effort: str | None = None) -> dict[str, Any]:
        """Request kwargs that turn reasoning on/off for `model`.

        Uses the method recorded in tf_capabilities.json (written by scripts/smoke_tf.py);
        falls back to chat_template_kwargs, the NVIDIA-documented switch.
        """
        method = self.capabilities.get(get(model).id, {}).get("thinking_method")
        return thinking_request(method or THINKING_METHODS[0], on, effort)

    def chat(
        self,
        model: str,
        messages: list[dict[str, Any]],
        *,
        purpose: str,
        thinking: bool | None = None,
        effort: str | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        spec = get(model)
        if thinking is not None:
            kwargs = {**self.think(spec.id, thinking, effort), **kwargs}
        return self._create(spec, purpose, messages=messages, **kwargs)

    def tools(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        purpose: str,
        parallel_tool_calls: bool | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        if parallel_tool_calls is not None:
            kwargs["parallel_tool_calls"] = parallel_tool_calls
        return self.chat(model, messages, purpose=purpose, tools=tools, **kwargs)

    def structured(
        self,
        model: str,
        messages: list[dict[str, Any]],
        schema: dict[str, Any],
        *,
        purpose: str,
        name: str = "result",
        use_response_format: bool | None = None,
        **kwargs: Any,
    ) -> tuple[Any, ChatResult]:
        """Return (validated JSON value, last ChatResult). One repair retry on invalid output."""
        spec = get(model)
        if use_response_format is None:
            caps = self.capabilities.get(spec.id, {})
            use_response_format = caps.get(
                "json_schema_recommended", caps.get("json_schema_accepted", True)
            )
        instruction = (
            "Reply with a single JSON value that validates against this JSON Schema. "
            "No prose, no code fences.\nSchema:\n" + json.dumps(schema)
        )
        msgs = [{"role": "system", "content": instruction}, *messages]
        rf_kwargs: dict[str, Any] = {}
        if use_response_format:
            rf_kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": name, "schema": schema, "strict": True},
            }
        try:
            result = self.chat(spec.id, msgs, purpose=purpose, **rf_kwargs, **kwargs)
        except openai.BadRequestError:
            if not rf_kwargs:
                raise
            # Backend rejected response_format; the schema is still in the prompt.
            self.capabilities.setdefault(spec.id, {})["json_schema_accepted"] = False
            result = self.chat(spec.id, msgs, purpose=purpose, **kwargs)
            rf_kwargs = {}

        if rf_kwargs and result.finish_reason == "length":
            # Constrained decoding can run away on numeric fields (measured on Lightning and
            # Ultra: digits until max_tokens). Fall back to the schema-in-prompt path.
            result = self.chat(spec.id, msgs, purpose=f"{purpose}:no_rf", **kwargs)
            rf_kwargs = {}
        error = self._validate(result.text, schema)
        if error is None:
            return extract_json(result.text), result
        repair = [
            *msgs,
            {"role": "assistant", "content": result.text},
            {
                "role": "user",
                "content": f"That output was invalid: {error}. Reply again with only the "
                "corrected JSON value.",
            },
        ]
        result = self.chat(spec.id, repair, purpose=f"{purpose}:repair", **rf_kwargs, **kwargs)
        error = self._validate(result.text, schema)
        if error is None:
            return extract_json(result.text), result
        raise StructuredOutputError(f"invalid structured output after repair: {error}")

    @staticmethod
    def _validate(text: str, schema: dict[str, Any]) -> str | None:
        try:
            value = extract_json(text)
        except ValueError as exc:
            return str(exc)
        try:
            jsonschema.validate(value, schema)
        except jsonschema.ValidationError as exc:
            return exc.message
        return None
