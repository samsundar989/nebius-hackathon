"""Run records as every report should read them: one source for NUMBERS.md, README and the site.

Overlays on the raw records in runs/<run>/<case>.json, each documented in DECISIONS:
  D-0056  re-judged verdicts (a libFuzzer slow-unit artifact is not a crash)
  D-0073  mosquitto re-gated with its CUnit suite
  D-0070  re-selected winners among several verified candidates (runs/winners.json),
          plus `ambiguous` from the cross-candidate differential
  D-0069  the hand semantic class of every verified diff (cases/arvo/semantic_adjudication.json)
Gate-side reporting only; nothing here feeds a worker or a gate verdict.
"""

from __future__ import annotations

import json
from functools import cache
from typing import Any

from leakproof.config import REPO_ROOT, RUNS_DIR
from leakproof.evidence import strength
from leakproof.fix import rank
from leakproof.semantic import CORRECT, change

# Re-judges applied in order: (output dir under runs/, decision). Each holds
# <case>/<run>/gate.json for the runs it re-gated.
REJUDGES = (("p3_rejudge_d0056", "D-0056"), ("p3_rejudge_d0073", "D-0073"))
ADJUDICATION = REPO_ROOT / "cases" / "arvo" / "semantic_adjudication.json"


@cache
def _semantic() -> dict[tuple[str, str], str]:
    if not ADJUDICATION.exists():
        return {}
    rows = json.loads(ADJUDICATION.read_text(encoding="utf-8"))["rows"]
    return {(r["case"], r["change"]): r["class"] for r in rows}


def semantic_class(case: str, diff: str) -> str | None:
    """Hand class of a verified diff, or None when it was never adjudicated."""
    return _semantic().get((case, change(diff)))


def output_stats(rec: dict[str, Any]) -> dict[str, int] | None:
    """The case's baseline corpus output stats: from the record (gate >= D-0074) or from
    runs/harness_output/ (measured afterwards for older runs); None when never measured."""
    corpus = (rec.get("gate") or {}).get("corpus") or {}
    if "stdout_distinct" in corpus:
        return {k: corpus[k] for k in ("clean_inputs", "stdout_distinct")}
    p = RUNS_DIR / "harness_output" / f"{rec['case']}.json"
    if p.exists():
        d = json.loads(p.read_text())
        if "stdout_distinct" in d:
            return {k: d[k] for k in ("clean_inputs", "stdout_distinct")}
    return None


@cache
def _winners() -> dict[str, Any]:
    p = RUNS_DIR / "winners.json"
    return json.loads(p.read_text()) if p.exists() else {}


def _find(workers: list[dict], who: dict) -> dict | None:
    return next(
        (
            w
            for w in workers
            if (w["hypothesis_id"], w["worker_index"], w.get("round", 1))
            == (who["hypothesis_id"], who["worker_index"], who.get("round", 1))
        ),
        None,
    )


def load(run: str, case_file: str) -> dict[str, Any]:
    rec = json.loads((RUNS_DIR / run / case_file).read_text())
    for out_dir, decision in REJUDGES:
        rejudge = RUNS_DIR / out_dir / rec["case"] / run / "gate.json"
        if not rejudge.exists():
            continue
        gate = json.loads(rejudge.read_text())
        new = {(g["hypothesis_id"], g["worker_index"]): g for g in gate["results"]}
        for w in rec.get("workers", []):
            g = new.get((w["hypothesis_id"], w["worker_index"]))
            if g is not None and w.get("round", 1) == 1:
                w.setdefault("verdict_as_run", w["verdict"])
                w["verdict"], w["gate"] = g["verdict"], g
        best = min(
            rec["workers"], key=lambda w: (rank(w["verdict"]), len(w.get("diff") or "x" * 10**6))
        )
        rec.setdefault("verdict_as_run", rec["verdict"])
        rec["verdict"] = best["verdict"]
        rec.setdefault("rejudged", []).append(decision)
        if best["verdict"] == "verified":
            rec["winner"] = {k: best.get(k, 1) for k in ("hypothesis_id", "worker_index", "round")}
            rec["winner"]["diff"] = best["diff"]
            rec["verdict_round1"] = "verified"
    sel = _winners().get(run, {}).get(rec["case"])
    if sel and rec.get("winner"):
        w = _find(rec["workers"], sel["new"])
        if w is not None:
            rec["winner_d0039"] = rec["winner"]
            rec["winner"] = {**sel["new"], "diff": w["diff"]}
            rec["selection"] = sel.get("log", [])
        rec["ambiguous"] = sel.get("ambiguous", False)
    if rec.get("winner"):
        rec["winner"]["semantic"] = semantic_class(rec["case"], rec["winner"]["diff"])
    stats = output_stats(rec)
    for w in rec.get("workers", []):
        if w.get("verdict") == "verified":
            w["semantic"] = semantic_class(rec["case"], w["diff"])
            w["evidence"] = strength((w.get("gate") or {}).get("checks") or {}, stats)
    if rec.get("winner"):
        win = _find(rec["workers"], rec["winner"])
        if win is not None and "evidence" in win:
            rec["winner"]["evidence"] = win["evidence"]
    return rec


def records(run: str) -> list[dict[str, Any]]:
    d = RUNS_DIR / run
    if not d.exists():
        return []
    return [load(run, p.name) for p in sorted(d.glob("*.json")) if p.name != "summary.json"]


def strict(rec: dict[str, Any]) -> bool:
    """Verified, and the chosen fix is adjudicated equivalent or different-but-correct."""
    return rec.get("verdict") == "verified" and (rec.get("winner") or {}).get("semantic") in CORRECT


def precision(recs: list[dict[str, Any]]) -> tuple[int, int, int]:
    """(correct, adjudicated, verified) over the distinct verified diffs of these records."""
    seen: dict[tuple[str, str], str | None] = {}
    for r in recs:
        for w in r.get("workers", []):
            if w.get("verdict") == "verified":
                seen[(r["case"], change(w["diff"]))] = w.get("semantic")
    cls = list(seen.values())
    return sum(c in CORRECT for c in cls), sum(c is not None for c in cls), len(cls)
