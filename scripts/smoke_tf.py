#!/usr/bin/env python3
"""Token Factory smoke test (kickoff E0 step 3.2). Spend cap: $0.50.

Per model (Ultra, Lightning, Nano, Super if up): hello call; thinking default / off via each
method; reasoning field name; json_schema honored?; parallel tool calls on a two-tool prompt.
Lightning only: 20 concurrent calls (rate-limit headers, 429s) and a 2-line Batch job.

Writes runs/smoke_tf_<ts>.json and leakproof/llm/tf_capabilities.json. Never prints keys.
Usage:  uv run python scripts/smoke_tf.py [--models ultra,lightning,nano,super] [--skip-batch]
        uv run python scripts/smoke_tf.py --poll-batch <batch_id>
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import sys
import time
from typing import Any

import openai

from leakproof.config import RUNS_DIR
from leakproof.llm.client import CAPABILITIES_PATH, LLMClient, extract_json, thinking_request
from leakproof.llm.ledger import CostLedger, LedgerEntry
from leakproof.llm.models import get

RUN_ID = "e0-smoke-tf"
REASON_PROMPT = [
    {
        "role": "user",
        "content": "A box has 3 red and 5 blue balls. I draw two without replacement. "
        "What is the probability both are blue? Answer with just the fraction.",
    }
]
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Current weather for a city",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string"}},
                "required": ["city"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_local_time",
            "description": "Current local time for a city",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string"}},
                "required": ["city"],
            },
        },
    },
]
# Deliberately odd key names that are NOT mentioned in the prompt: if the output uses them,
# the backend enforced response_format (constrained decoding) rather than the model guessing.
ODD_SCHEMA = {
    "type": "object",
    "properties": {
        "zq_capital": {"type": "string"},
        "zq_population_millions": {"type": "number"},
    },
    "required": ["zq_capital", "zq_population_millions"],
    "additionalProperties": False,
}


def summarize(r: Any) -> dict[str, Any]:
    return {
        "latency_s": round(r.latency_s, 2),
        "prompt_tokens": r.prompt_tokens,
        "completion_tokens": r.completion_tokens,
        "reasoning_tokens": r.reasoning_tokens,
        "reasoning_field": r.reasoning_field,
        "reasoning_chars": len(r.reasoning),
        "finish_reason": r.finish_reason,
        "text": r.text[:200],
        "usd": round(r.usd, 6),
    }


def attempt(fn: Any) -> dict[str, Any]:
    try:
        return fn()
    except openai.APIStatusError as exc:
        return {"error": f"HTTP {exc.status_code}: {str(exc.message)[:300]}"}
    except Exception as exc:  # noqa: BLE001 - smoke test records every failure
        return {"error": f"{type(exc).__name__}: {str(exc)[:300]}"}


def probe_model(c: LLMClient, short: str) -> dict[str, Any]:
    spec = get(short)
    out: dict[str, Any] = {"id": spec.id}
    cap = 4096

    out["hello"] = attempt(
        lambda: summarize(
            c.chat(
                spec.id,
                [{"role": "user", "content": "Say hello in five words."}],
                purpose="smoke:hello",
                max_tokens=cap,
            )
        )
    )
    if "error" in out["hello"]:
        return out

    out["think_default"] = attempt(
        lambda: summarize(c.chat(spec.id, REASON_PROMPT, purpose="smoke:think", max_tokens=cap))
    )
    for method in ("chat_template_kwargs", "reasoning_effort"):
        out[f"think_off_{method}"] = attempt(
            lambda m=method: summarize(
                c.chat(
                    spec.id,
                    REASON_PROMPT,
                    purpose=f"smoke:think_off:{m}",
                    max_tokens=cap,
                    **thinking_request(m, False),
                )
            )
        )
    for effort in ("low", "high"):
        out[f"think_effort_{effort}"] = attempt(
            lambda e=effort: summarize(
                c.chat(
                    spec.id,
                    REASON_PROMPT,
                    purpose=f"smoke:effort:{e}",
                    max_tokens=cap,
                    **thinking_request("reasoning_effort", True, e),
                )
            )
        )

    off = thinking_request(out_best_method(out) or "chat_template_kwargs", False)

    def json_schema_probe() -> dict[str, Any]:
        r = c.chat(
            spec.id,
            [{"role": "user", "content": "Tell me about France as JSON."}],
            purpose="smoke:json_schema",
            max_tokens=1024,
            response_format={
                "type": "json_schema",
                "json_schema": {"name": "country", "schema": ODD_SCHEMA, "strict": True},
            },
            **off,
        )
        res = summarize(r)
        try:
            extract_json(r.text)
            res["valid_json"] = True
        except ValueError:
            res["valid_json"] = False
        # Enforcement is visible even in truncated output: the unprompted keys appear.
        res["schema_keys_used"] = all(k in r.text for k in ODD_SCHEMA["properties"])
        return res

    out["json_schema"] = attempt(json_schema_probe)

    def tools_probe() -> dict[str, Any]:
        r = c.tools(
            spec.id,
            [{"role": "user", "content": "What's the weather and the local time in Paris?"}],
            TOOLS,
            purpose="smoke:tools",
            parallel_tool_calls=True,
            max_tokens=1024,
            **off,
        )
        res = summarize(r)
        res["tool_calls"] = [t["name"] for t in r.tool_calls]
        return res

    out["tools_parallel"] = attempt(tools_probe)
    return out


def out_best_method(out: dict[str, Any]) -> str | None:
    """The thinking-off method that actually suppressed reasoning (fewest reasoning tokens)."""
    default = out.get("think_default", {})
    best, best_tokens = None, None
    for method in ("chat_template_kwargs", "reasoning_effort"):
        r = out.get(f"think_off_{method}", {})
        if "error" in r:
            continue
        tokens = r["reasoning_tokens"] or (r["reasoning_chars"] and r["completion_tokens"])
        if best_tokens is None or tokens < best_tokens:
            best, best_tokens = method, tokens
    if best is None or "error" in default:
        return best
    default_tokens = default["reasoning_tokens"] or default["completion_tokens"]
    return best if best_tokens is not None and best_tokens < default_tokens else None


def concurrency_probe(c: LLMClient, n: int = 20) -> dict[str, Any]:
    spec = get("lightning")
    off = c.think(spec.id, False)
    t0 = time.monotonic()

    def one(i: int) -> dict[str, Any]:
        try:
            r = c.chat(
                spec.id,
                [{"role": "user", "content": f"Reply with the number {i}."}],
                purpose="smoke:concurrency",
                max_tokens=32,
                **off,
            )
            return {
                "ok": True,
                "attempts": r.attempts,
                "latency_s": r.latency_s,
                "rl": r.ratelimit_headers,
            }
        except openai.APIStatusError as exc:
            return {"ok": False, "status": exc.status_code}

    # Count raw 429s: run without client-side retries so throttling is visible.
    saved = c.max_retries
    c.max_retries = 0
    try:
        with cf.ThreadPoolExecutor(max_workers=n) as pool:
            results = list(pool.map(one, range(n)))
    finally:
        c.max_retries = saved
    wall = time.monotonic() - t0
    lat = sorted(r["latency_s"] for r in results if r["ok"])
    headers = next((r["rl"] for r in results if r.get("rl")), {})
    return {
        "n": n,
        "ok": sum(r["ok"] for r in results),
        "status_counts": {
            str(s): sum(1 for r in results if r.get("status") == s)
            for s in {r.get("status") for r in results if not r["ok"]}
        },
        "wall_s": round(wall, 2),
        "latency_p50_s": round(lat[len(lat) // 2], 2) if lat else None,
        "latency_max_s": round(lat[-1], 2) if lat else None,
        "ratelimit_headers_sample": headers,
    }


def batch_submit(c: LLMClient) -> dict[str, Any]:
    spec = get("lightning")
    lines = [
        {
            "custom_id": f"smoke-{i}",
            "method": "POST",
            "url": "/v1/chat/completions",
            "body": {
                "model": spec.id,
                "messages": [{"role": "user", "content": q}],
                "max_tokens": 64,
                "chat_template_kwargs": {"enable_thinking": False},
            },
        }
        for i, q in enumerate(["What is 2+2? Just the number.", "Name one prime above 10."])
    ]
    path = RUNS_DIR / "smoke_batch_input.jsonl"
    path.write_text("".join(json.dumps(line) + "\n" for line in lines))
    sdk = c._sdk
    t0 = time.monotonic()
    f = sdk.files.create(file=path.open("rb"), purpose="batch")
    b = sdk.batches.create(
        input_file_id=f.id, endpoint="/v1/chat/completions", completion_window="24h"
    )
    return {
        "file_id": f.id,
        "batch_id": b.id,
        "status": b.status,
        "submit_s": round(time.monotonic() - t0, 2),
        "submitted_at": time.time(),
    }


def batch_poll(c: LLMClient, batch_id: str) -> dict[str, Any]:
    sdk = c._sdk
    b = sdk.batches.retrieve(batch_id)
    res: dict[str, Any] = {
        "batch_id": batch_id,
        "status": b.status,
        "request_counts": getattr(b, "request_counts", None) and b.request_counts.model_dump(),
    }
    if b.status == "completed" and b.output_file_id:
        content = sdk.files.content(b.output_file_id).text
        spec = get("lightning")
        rows = [json.loads(line) for line in content.splitlines() if line.strip()]
        usd = 0.0
        answers = []
        for row in rows:
            body = row.get("response", {}).get("body", {})
            usage = body.get("usage", {})
            # Batch is billed at 50% of list price.
            usd += spec.cost(usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)) / 2
            choices = body.get("choices") or [{}]
            answers.append(choices[0].get("message", {}).get("content"))
        c.ledger.record(
            LedgerEntry(
                model=spec.id,
                purpose="smoke:batch",
                run_id=RUN_ID,
                prompt_tokens=0,
                completion_tokens=0,
                reasoning_tokens=0,
                usd=usd,
                latency_s=0.0,
                kind="batch",
                note=f"batch {batch_id}, 50% rate",
            )
        )
        res.update(
            answers=answers,
            usd=usd,
            completed_at=getattr(b, "completed_at", None),
            created_at=getattr(b, "created_at", None),
        )
    return res


def write_capabilities(results: dict[str, Any]) -> dict[str, Any]:
    caps: dict[str, Any] = (
        json.loads(CAPABILITIES_PATH.read_text()) if CAPABILITIES_PATH.exists() else {}
    )
    for out in results["models"].values():
        if "error" in out.get("hello", {}):
            caps[out["id"]] = {"available": False, "checked": time.strftime("%Y-%m-%d")}
            continue
        js = out.get("json_schema", {})
        caps[out["id"]] = {
            "available": True,
            "thinking_method": out_best_method(out),
            "reasoning_field": out.get("think_default", {}).get("reasoning_field"),
            "json_schema_accepted": "error" not in js,
            "json_schema_enforced": bool(js.get("schema_keys_used")),
            # Recommend response_format only when it also produced complete, valid JSON.
            "json_schema_recommended": bool(js.get("valid_json"))
            and js.get("finish_reason") != "length",
            "parallel_tool_calls": len(out.get("tools_parallel", {}).get("tool_calls", [])) >= 2,
            "checked": time.strftime("%Y-%m-%d"),
        }
    CAPABILITIES_PATH.write_text(json.dumps(caps, indent=2, sort_keys=True) + "\n")
    return caps


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="ultra,lightning,nano,super")
    ap.add_argument("--skip-batch", action="store_true")
    ap.add_argument("--skip-concurrency", action="store_true")
    ap.add_argument("--poll-batch")
    args = ap.parse_args()

    ledger = CostLedger(budget=0.50, ledger_cap=5.0)
    c = LLMClient(ledger=ledger, run_id=RUN_ID, max_retries=3)
    if args.poll_batch:
        print(json.dumps(batch_poll(c, args.poll_batch), indent=2))
        return 0

    results: dict[str, Any] = {"started": time.strftime("%Y-%m-%dT%H:%M:%S"), "models": {}}
    for short in args.models.split(","):
        print(f"== {short}", file=sys.stderr)
        results["models"][short] = probe_model(c, short)
    caps = write_capabilities(results)
    c.capabilities = caps
    if not args.skip_concurrency:
        print("== concurrency", file=sys.stderr)
        results["concurrency_lightning"] = attempt(lambda: concurrency_probe(c))
    if not args.skip_batch:
        print("== batch", file=sys.stderr)
        results["batch_lightning"] = attempt(lambda: batch_submit(c))
    results["spent_usd"] = round(ledger.spent, 6)
    out = RUNS_DIR / f"smoke_tf_{time.strftime('%Y%m%d_%H%M%S')}.json"
    out.write_text(json.dumps(results, indent=2))
    print(json.dumps(results, indent=2))
    print(f"wrote {out}; spent ${ledger.spent:.4f}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
