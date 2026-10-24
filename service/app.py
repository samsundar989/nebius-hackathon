"""Leakproof demo service (Render free web service).

GET  /healthz   liveness (the dashboard pings it to wake a sleeping instance)
POST /run       one Juliet case: live when DEMO_ENABLED=true and under the caps, otherwise a
                labelled recorded result from a real run (service/recorded/*.json)

Live runs stay off in this version: a live run compiles and executes model-written C next to the
Token Factory key, which needs a privilege-separated runner first (no key in the child's
environment or /proc view). Until then every response is recorded and says so.
"""

from __future__ import annotations

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


@app.post("/run")
def run(request: Request) -> dict:
    ok, why = _allowed(request.client.host if request.client else "?")
    if not ok:
        return _recorded(why)
    # Live path intentionally not wired yet (see module docstring).
    return _recorded("live runner not enabled in this build")
