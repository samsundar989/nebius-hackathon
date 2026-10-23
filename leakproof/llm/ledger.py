"""Append-only cost ledger (runs/cost_ledger.jsonl) and the budget guard.

Two limits apply:
- process budget (LEAKPROOF_BUDGET_USD): spend recorded by this ledger object since it was created;
- ledger cap (LEAKPROOF_LEDGER_CAP_USD, optional): total of every entry in the file, i.e. the
  whole experiment's spend across processes.
Both are checked before every call and after recording it.
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from leakproof.config import RUNS_DIR, budget_usd


class BudgetExceeded(RuntimeError):
    """Raised instead of making (or after recording) a call that crosses a spend limit."""


@dataclass
class LedgerEntry:
    model: str
    purpose: str
    run_id: str
    prompt_tokens: int
    completion_tokens: int
    reasoning_tokens: int
    usd: float
    latency_s: float
    kind: str = "chat"  # chat | batch | compute
    ok: bool = True
    note: str = ""
    ts: float = field(default_factory=time.time)


class CostLedger:
    def __init__(
        self,
        path: Path | None = None,
        budget: float | None = None,
        ledger_cap: float | None = None,
    ) -> None:
        self.path = path or RUNS_DIR / "cost_ledger.jsonl"
        self.budget = budget if budget is not None else budget_usd()
        cap_env = os.environ.get("LEAKPROOF_LEDGER_CAP_USD")
        self.ledger_cap = (
            ledger_cap if ledger_cap is not None else (float(cap_env) if cap_env else None)
        )
        self.spent = 0.0
        self.by_model: dict[str, float] = {}
        self._lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def file_total(self) -> float:
        if not self.path.exists():
            return 0.0
        total = 0.0
        for line in self.path.read_text().splitlines():
            if line.strip():
                total += float(json.loads(line).get("usd", 0.0))
        return total

    def check(self) -> None:
        """Raise BudgetExceeded if no further spend is allowed."""
        if self.spent >= self.budget:
            raise BudgetExceeded(
                f"process budget exhausted: spent ${self.spent:.4f} of ${self.budget:.2f}"
            )
        if self.ledger_cap is not None:
            total = self.file_total()
            if total >= self.ledger_cap:
                raise BudgetExceeded(
                    f"ledger cap reached: ${total:.4f} recorded of ${self.ledger_cap:.2f}"
                )

    def record(self, entry: LedgerEntry) -> None:
        with self._lock:
            with self.path.open("a") as fh:
                fh.write(json.dumps(asdict(entry)) + "\n")
            self.spent += entry.usd
            self.by_model[entry.model] = self.by_model.get(entry.model, 0.0) + entry.usd
