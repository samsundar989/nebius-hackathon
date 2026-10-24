#!/usr/bin/env python3
"""Markdown tables for a fix run (runs/<run_id>/*.json) — the numbers REPORT_SHIP.md quotes.

Usage: scripts/run_report.py e1_juliet60_v1
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict

from leakproof.config import RUNS_DIR


def sandbox_units(run_id: str) -> float:
    """Sandboxes `units` the ledger recorded for this run's cases and gate runs (D-0057)."""
    path = RUNS_DIR / "cost_ledger.jsonl"
    if not path.exists():
        return 0.0
    total = 0.0
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            e = json.loads(line)
        except ValueError:
            continue
        rid = e.get("run_id", "")
        if e.get("kind") == "compute" and (rid == run_id or rid.startswith(f"{run_id}:")):
            total += float(e.get("units", 0.0))
    return total


def main() -> int:
    run = RUNS_DIR / sys.argv[1]
    recs = [
        json.loads(p.read_text()) for p in sorted(run.glob("*.json")) if p.name != "summary.json"
    ]
    by_cwe: dict[str, Counter] = defaultdict(Counter)
    reasons: Counter = Counter()
    worker_status: Counter = Counter()
    usd = 0.0
    for r in recs:
        cwe = (r.get("finding") or {}).get("cwe_guess") or r["case"].split("_")[0]
        head = r["verdict"].split(":", 1)[0]
        by_cwe[cwe]["cases"] += 1
        by_cwe[cwe][head] += 1
        crash_gone = any(
            (w.get("gate") or {}).get("checks", {}).get("patched", {}).get("status") == "pass"
            for w in r.get("workers", [])
        )
        by_cwe[cwe]["raw_crash_gone"] += crash_gone
        if head != "verified":
            reasons[r["verdict"]] += 1
        for w in r.get("workers", []):
            worker_status[
                w["verdict"].split(":", 1)[0] if w["verdict"] != "verified" else "verified"
            ] += 1
        usd += r.get("usd", 0.0)
    cols = [
        "cases",
        "raw_crash_gone",
        "verified",
        "silenced_only",
        "rejected",
        "build_failed",
        "no_candidate",
        "inconclusive",
        "error",
    ]
    print("| CWE | " + " | ".join(cols) + " |")
    print("|---" * (len(cols) + 1) + "|")
    total: Counter = Counter()
    for cwe, c in sorted(by_cwe.items()):
        total.update(c)
        print(f"| {cwe} | " + " | ".join(str(c.get(k, 0)) for k in cols) + " |")
    print("| **all** | " + " | ".join(f"**{total.get(k, 0)}**" for k in cols) + " |")
    n, v = total["cases"], total["verified"]
    print(
        f"\nVerified {v}/{n} ({v / max(n, 1):.0%}); crash gone (raw) {total['raw_crash_gone']}/{n}; "
        f"spend ${usd:.4f}; $/verified {usd / v:.4f}"
        if v
        else f"\nVerified 0/{n}; spend ${usd:.4f}"
    )
    units = sandbox_units(sys.argv[1])
    if units:
        print(f"Sandboxes compute: {units:.4f} units (not billed during the beta; not in $)")
    lat = sorted(r["elapsed_s"] for r in recs)
    if lat:
        print(f"Case wall time p50 {lat[len(lat) // 2]:.0f} s, max {lat[-1]:.0f} s")
    print("\nNon-verified cases by verdict:")
    for k, c in reasons.most_common():
        print(f"- {k}: {c}")
    print(
        "\nWorker outcomes (all workers): "
        + ", ".join(f"{k} {c}" for k, c in worker_status.most_common())
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
