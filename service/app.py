"""Leakproof demo service (Render free web service).

GET  /healthz   liveness (the dashboard pings it to wake a sleeping instance)
POST /run       one Juliet case: live when DEMO_ENABLED=true and under the caps, otherwise a
                labelled recorded result from a real run (service/recorded/*.json)
POST /reverify  "Re-verify without AI" (review #17 order 4): the full gate, re-run here on a
                stored worker candidate (service/reverify/*.json, from real run records), with
                no model call; returns today's verdict next to the one the gate gave then

A live run (D-0061): one whitelisted Juliet case, an Ultra plan, 2 Lightning workers and the gate
(its own process), all on `LocalProcessRunner`: model-written code is built and run as `nobody`
with a cleared environment, so it can neither inherit nor read the API key. One run at a time;
caps and the service budget (LEAKPROOF_BUDGET_USD) fall back to a labelled recorded result.

Caps for leaving it on during judging (review #11 order 5), all checked before any model call:
  DEMO_TOTAL_USD    model spend for this instance's lifetime (default 3.00)
  DEMO_DAILY_USD    model spend per rolling 24 h (default 0.50)
  DEMO_MAX_RUNS_PER_DAY, DEMO_MAX_RUNS_PER_IP_10MIN   run counts (25, 3)
A request may name a case ({"case": "<Juliet id>"}); only ids in juliet/cases.txt run live.
DEMO_PASSCODE, when set, must match the request's {"passcode": ...} for a live run (it is in the
Devpost testing instructions); without it /run returns a labelled recorded result. /reverify
costs no model money and needs no passcode; it has its own per-visitor cap
(DEMO_MAX_REVERIFY_PER_IP_10MIN, default 6) and shares the one-at-a-time lock with /run.
The caps live in memory: a restart (Render free instances sleep when idle) resets them, so the
real bound over a judging window is the daily cap times the days live runs are on.
"""

from __future__ import annotations

import asyncio
import hmac
import json
import os
import random
import threading
import time
from collections import deque
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

RECORDED = sorted((Path(__file__).parent / "recorded").glob("*.json"))
app = FastAPI(title="leakproof-demo")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.environ.get("SITE_ORIGIN", "*")],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
# In-memory caps: they reset on every restart (Render free instances sleep and restart).
_lock = threading.Lock()
_day: deque[float] = deque()
_by_ip: dict[str, deque[float]] = {}
_spend: deque[tuple[float, float]] = deque()  # (time, usd) of finished live runs
CASES = Path(__file__).parent / "juliet" / "cases.txt"
REVERIFY = Path(__file__).parent / "reverify"
_reverify_by_ip: dict[str, deque[float]] = {}


def _passcode_ok(body: dict) -> bool:
    want = os.environ.get("DEMO_PASSCODE", "")
    got = str(body.get("passcode") or "")
    return not want or hmac.compare_digest(got.encode(), want.encode())


def _money_left() -> tuple[bool, str]:
    """Both USD caps, before a run starts."""
    now = time.time()
    total = float(os.environ.get("DEMO_TOTAL_USD", "3.00"))
    daily = float(os.environ.get("DEMO_DAILY_USD", "0.50"))
    with _lock:
        while _spend and now - _spend[0][0] > 86400:
            _spend.popleft()
        spent_day = sum(u for _, u in _spend)
    spent_all = _ledger.spent if _ledger is not None else 0.0
    if spent_all >= total:
        return False, f"the demo's total budget (${total:.2f}) is used up"
    if spent_day >= daily:
        return False, f"today's demo budget (${daily:.2f}) is used up"
    return True, ""


def _allowed(ip: str) -> tuple[bool, str]:
    if os.environ.get("DEMO_ENABLED", "false").lower() != "true":
        return False, "live runs are disabled"
    now = time.time()
    per_day = int(os.environ.get("DEMO_MAX_RUNS_PER_DAY", "25"))
    per_ip = int(os.environ.get("DEMO_MAX_RUNS_PER_IP_10MIN", "3"))
    with _lock:
        while _day and now - _day[0] > 86400:
            _day.popleft()
        q = _by_ip.setdefault(ip, deque())
        while q and now - q[0] > 600:
            q.popleft()
        if len(_day) >= per_day:
            return False, "daily demo cap reached"
        if len(q) >= per_ip:
            return False, "per-visitor cap reached (3 per 10 minutes)"
        _day.append(now)
        q.append(now)
    return True, ""


def _recorded(reason: str) -> dict:
    if not RECORDED:
        return {"verdict": "unavailable", "recorded": True, "reason": reason}
    rec = json.loads(random.choice(RECORDED).read_text())
    return rec | {"recorded": True, "reason": reason}


def _isolation() -> str:
    from leakproof.runner.local_process import isolation

    return isolation()


@app.get("/healthz")
def healthz() -> dict:
    return {
        "ok": True,
        "live": os.environ.get("DEMO_ENABLED", "false").lower() == "true",
        "isolation": _isolation(),
    }


_busy = threading.Lock()
_ledger = None


def _live(case: str | None = None) -> dict:
    global _ledger
    import tempfile

    from leakproof.fix import fix_case
    from leakproof.llm import CostLedger, LLMClient
    from leakproof.runner.local_process import LocalProcessRunner

    if _ledger is None:
        _ledger = CostLedger(
            path=Path(tempfile.gettempdir()) / "demo_ledger.jsonl",
            budget=min(
                float(os.environ.get("LEAKPROOF_BUDGET_USD", "0.50")),
                float(os.environ.get("DEMO_TOTAL_USD", "3.00")),
            ),
        )
    _ledger.check()  # BudgetExceeded once the service budget is spent
    case_id = case or random.choice(CASES.read_text().split())
    spent0 = _ledger.spent
    client = LLMClient(ledger=_ledger, run_id=f"demo:{case_id}")
    with tempfile.TemporaryDirectory() as tmp:
        rec = fix_case(
            case_id,
            Path(tmp),
            client,
            LocalProcessRunner(),
            planner_model="ultra",
            n_workers=2,
            audit_model=None,
        )
    with _lock:
        _spend.append((time.time(), _ledger.spent - spent0))
    return {
        "case": rec["case"],
        "verdict": rec["verdict"],
        "usd": rec.get("usd"),
        "elapsed_s": rec.get("elapsed_s"),
        "finding": {k: (rec.get("finding") or {}).get(k) for k in ("kind", "location")},
        "root_cause": (rec.get("plan") or {}).get("root_cause"),
        "winner": (rec.get("winner") or {}).get("diff"),
        "workers": [
            {"id": f"{w['hypothesis_id']}·w{w['worker_index']}", "verdict": w["verdict"]}
            for w in rec.get("workers", [])
        ],
        "recorded": False,
    }


@app.post("/run")
async def run(request: Request) -> dict:
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001 - no body or not JSON: a random allowed case
        body = {}
    body = body if isinstance(body, dict) else {}
    case = body.get("case")
    if case is not None and case not in CASES.read_text().split():
        return _recorded("that case is not on the demo's allow-list")
    if not _passcode_ok(body):
        return _recorded("live runs need the passcode from the testing instructions")
    if _isolation() != "nobody":
        # Model-written code must not run as the user that holds the API key.
        return _recorded("live runs need process isolation, which this host does not allow")
    ok, why = _money_left()
    if not ok:
        return _recorded(why)
    ok, why = _allowed(request.client.host if request.client else "?")
    if not ok:
        return _recorded(why)
    return await asyncio.to_thread(_run_locked, case)


def _run_locked(case: str | None) -> dict:
    if not _busy.acquire(blocking=False):
        return _recorded("another live run is in progress")
    try:
        return _live(case)
    except Exception as exc:  # noqa: BLE001 - budget, API or build failure: never a 500
        return _recorded(f"live run unavailable ({type(exc).__name__})")
    finally:
        _busy.release()


def _reverify_allowed(ip: str) -> bool:
    now = time.time()
    per_ip = int(os.environ.get("DEMO_MAX_REVERIFY_PER_IP_10MIN", "6"))
    with _lock:
        q = _reverify_by_ip.setdefault(ip, deque())
        while q and now - q[0] > 600:
            q.popleft()
        if len(q) >= per_ip:
            return False
        q.append(now)
    return True


def _reverify(case: str, which: str) -> dict:
    """The gate, in its own process, on a stored candidate: no planner, no workers, no model."""
    import tempfile

    from leakproof.cases.juliet import JulietCase
    from leakproof.fix import run_gate_process
    from leakproof.runner.local_process import LocalProcessRunner

    stored = json.loads((REVERIFY / f"{case}.json").read_text())[which]
    jcase = JulietCase.load(case)
    t0 = time.monotonic()
    baseline = jcase.prepare(LocalProcessRunner())
    cand = {k: stored[k] for k in ("hypothesis_id", "worker_index", "strategy", "files", "diff")}
    with tempfile.TemporaryDirectory() as tmp:
        gate = run_gate_process(
            case, baseline.ref, None, jcase.finding, [cand], Path(tmp), runner_name="local"
        )
    r = gate["results"][0]
    return {
        "case": case,
        "candidate": which,
        "diff": stored["diff"],
        "source": stored["source"],
        "verdict_then": stored["verdict_then"],
        "verdict": r["verdict"],
        "matches": r["verdict"] == stored["verdict_then"],
        "unpatched": gate["unpatched"],
        "checks": r["checks"],
        "elapsed_s": round(time.monotonic() - t0, 2),
        "model_calls": 0,
        "usd": 0.0,
    }


@app.get("/reverify")
def reverify_list() -> dict:
    """Which stored candidates exist: case -> the verdicts the gate gave them then."""
    out = {}
    for p in sorted(REVERIFY.glob("*.json")):
        d = json.loads(p.read_text())
        out[p.stem] = {k: d[k]["verdict_then"] for k in ("verified", "rejected") if k in d}
    return {"cases": out}


@app.post("/reverify")
async def reverify(request: Request) -> dict:
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001 - no body: a random case's verified candidate
        body = {}
    body = body if isinstance(body, dict) else {}
    which = body.get("candidate", "verified")
    if which not in ("verified", "rejected"):
        return {"error": "candidate must be 'verified' or 'rejected'"}
    have = {p.stem for p in REVERIFY.glob("*.json") if which in json.loads(p.read_text())}
    case = body.get("case") or random.choice(sorted(have))
    if case not in have:
        return {"error": f"no stored {which} candidate for that case"}
    if not _reverify_allowed(request.client.host if request.client else "?"):
        return {"error": "per-visitor cap reached (re-verify: 6 per 10 minutes)"}
    return await asyncio.to_thread(_reverify_locked, case, which)


def _reverify_locked(case: str, which: str) -> dict:
    if not _busy.acquire(blocking=False):
        return {"error": "another run is in progress; try again in a minute"}
    try:
        return _reverify(case, which)
    except Exception as exc:  # noqa: BLE001 - never a 500
        return {"error": f"re-verify failed ({type(exc).__name__}: {str(exc)[:200]})"}
    finally:
        _busy.release()
