"""Append-only cost ledger (runs/cost_ledger.jsonl) and the budget guard.

Two limits apply:
- process budget (LEAKPROOF_BUDGET_USD): spend recorded by this ledger object since it was created;
- ledger cap (LEAKPROOF_LEDGER_CAP_USD, optional): total of every entry in the file, i.e. the
  whole experiment's spend across processes.
Both are checked before every call and after recording it.
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
import threading
import time
from collections.abc import Iterator
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import IO, Any

from leakproof.config import RUNS_DIR, budget_usd

if os.name == "nt":
    import msvcrt

    def _lock_file(fh: IO[Any]) -> None:
        fh.seek(0)
        msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)

    def _unlock_file(fh: IO[Any]) -> None:
        fh.seek(0)
        msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)

else:
    import fcntl

    def _lock_file(fh: IO[Any]) -> None:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _unlock_file(fh: IO[Any]) -> None:
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


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
    units: float = 0.0  # compute: provider-reported units, not USD (Sandboxes: D-0057)
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

    @contextlib.contextmanager
    def _file_lock(self) -> Iterator[None]:
        """Cross-process lock on a sidecar file (D-0054): the gate subprocesses and the batch
        process append to the same ledger, and on Windows interleaved appends corrupted a line
        (p4_juliet401x100_r1). The threading lock only covers one process."""
        lock_path = self.path.with_suffix(".lock")
        with open(lock_path, "a+b") as fh:
            for _ in range(600):
                try:
                    _lock_file(fh)
                    break
                except OSError:
                    time.sleep(0.05)
            else:
                raise RuntimeError(f"could not lock {lock_path}")
            try:
                yield
            finally:
                _unlock_file(fh)

    def file_total(self) -> float:
        if not self.path.exists():
            return 0.0
        total, bad = 0.0, 0
        with self._file_lock():
            text = self.path.read_text(encoding="utf-8")
        for line in text.splitlines():
            if not line.strip():
                continue
            try:
                total += float(json.loads(line).get("usd", 0.0))
            except (ValueError, AttributeError):
                bad += 1  # counted, never silently: one bad line must not stop every check
        if bad:
            print(f"[ledger] {bad} unparsable line(s) in {self.path}", file=sys.stderr)
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
        with self._lock, self._file_lock():
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(asdict(entry)) + "\n")
            self.spent += entry.usd
            self.by_model[entry.model] = self.by_model.get(entry.model, 0.0) + entry.usd
