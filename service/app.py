"""Leakproof demo service (Render free web service).

GET  /healthz   liveness (the dashboard pings it to wake a sleeping instance)
POST /run       one Juliet case: live when DEMO_ENABLED=true and under the caps, otherwise a
                labelled recorded result from a real run (service/recorded/*.json)

A live run (D-0061): one whitelisted Juliet case, an Ultra plan, 2 Lightning workers and the gate
(its own process), all on `LocalProcessRunner`: model-written code is built and run as `nobody`
with a cleared environment, so it can neither inherit nor read the API key. One run at a time;
caps and the service budget (LEAKPROOF_BUDGET_USD) fall back to a labelled recorded result.

Caps for leaving it on during judging (review #11 order 5), all checked before any model call:
  DEMO_TOTAL_USD    model spend for this instance's lifetime (default 2.00)
  DEMO_DAILY_USD    model spend per rolling 24 h (default 0.50)
  DEMO_MAX_RUNS_PER_DAY, DEMO_MAX_RUNS_PER_IP_10MIN   run counts (25, 3)
A request may name a case ({"case": "<Juliet id>"}); only ids in juliet/cases.txt run live.
The caps live in memory: a restart (Render free instances sleep when idle) resets them, so the
real bound over a judging window is the daily cap times the days live runs are on.
"""

from __future__ import annotations

import asyncio
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


def _money_left() -> tuple[bool, str]:
    """Both USD caps, before a run starts."""
    now = time.time()
    total = float(os.environ.get("DEMO_TOTAL_USD", "2.00"))
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


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True, "live": os.environ.get("DEMO_ENABLED", "false").lower() == "true"}


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
                float(os.environ.get("DEMO_TOTAL_USD", "2.00")),
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
    case = (body or {}).get("case") if isinstance(body, dict) else None
    if case is not None and case not in CASES.read_text().split():
        return _recorded("that case is not on the demo's allow-list")
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
