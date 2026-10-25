#!/usr/bin/env python3
"""Build the static dashboard's data (site/data/*.json) from runs/ (P5.2).

  scripts/build_site.py            -> site/data/{index,calibration,leaderboard}.json
                                      + site/data/runs/<run>.json

Every number on the page comes from these files, regenerated from the run records; nothing is
typed into the HTML. Secrets never appear in run records (ledger and .env are not read).
"""

from __future__ import annotations

import json
import sys
from collections import Counter

from leakproof.config import REPO_ROOT, RUNS_DIR

SITE = REPO_ROOT / "site" / "data"
RUNS = [
    ("p3_arvo27_r1", "ARVO: 27 calibrated real OSS-Fuzz cases", "arvo"),
    ("e1_juliet60_v1", "Juliet smoke set: 60 cases (CWE-401/415/416)", "juliet"),
    ("p4_juliet401x100_r1", "Juliet CWE-401 sample: 100 cases", "juliet"),
    ("p2_sandboxes_juliet3", "Nebius Sandboxes: 3 Juliet cases, gate offline", "juliet"),
]
CHECKS = [
    "unpatched_trips",
    "diff_scope",
    "build",
    "compiled",
    "patched",
    "tests",
    "behavior",
    "differential",
    "refuzz",
    "safe_fix",
]


def v0_verdict(checks: dict) -> str:
    from leakproof.gate import Check, decide

    return decide(
        {
            k: Check(v["status"], v["detail"])
            for k, v in checks.items()
            if k not in ("differential", "refuzz", "safe_fix")
        }
    )


def case_view(rec: dict) -> dict:
    workers = []
    for w in rec.get("workers", []):
        g = w.get("gate") or {}
        checks = g.get("checks") or {}
        workers.append(
            {
                "id": f"{w['hypothesis_id']}·w{w['worker_index']}",
                "verdict": w["verdict"],
                "v0": v0_verdict(checks) if checks else None,
                "checks": {
                    k: {"s": checks[k]["status"], "d": checks[k]["detail"][:400]}
                    for k in CHECKS
                    if k in checks
                },
                "audit": (w.get("audit") or {}).get("flags", []),
                "diff": (w.get("diff") or "")[:6000],
            }
        )
    gated = [w for w in workers if w["checks"]]
    arvo = rec.get("arvo") or {}
    lineage = rec.get("lineage") or {}
    return {
        "case": rec["case"],
        "project": arvo.get("project") or rec["case"].split("__")[0],
        "verdict": rec["verdict"],
        "raw": any(w["checks"].get("patched", {}).get("s") == "pass" for w in gated),
        "v0": any(w["v0"] == "verified" for w in gated),
        "finding": {
            k: (rec.get("finding") or {}).get(k) for k in ("kind", "location", "cwe_guess")
        },
        "root_cause": (rec.get("plan") or {}).get("root_cause", ""),
        "planner": rec.get("planner_model"),
        "usd": rec.get("usd", 0.0),
        "usd_by_model": rec.get("usd_by_model", {}),
        "elapsed_s": rec.get("elapsed_s"),
        "gate_version": (rec.get("gate") or {}).get("gate_version", "v0"),
        "dev_fix": arvo.get("patch_url"),
        "winner": (rec.get("winner") or {}).get("diff"),
        "workers": workers,
        "lineage": [
            {k: e.get(k) for k in ("op", "parent", "image", "network", "exit", "s", "usd")}
            for e in (lineage.get("workers") or []) + (lineage.get("gate") or [])
        ],
    }


def main() -> int:
    (SITE / "runs").mkdir(parents=True, exist_ok=True)
    index = []
    for run, label, suite in RUNS:
        run_dir = RUNS_DIR / run
        if not run_dir.exists():
            continue
        cases = [
            case_view(json.loads(p.read_text()))
            for p in sorted(run_dir.glob("*.json"))
            if p.name != "summary.json"
        ]
        verdicts = Counter(c["verdict"].split(":", 1)[0] for c in cases)
        usd = sum(c["usd"] for c in cases)
        verified = verdicts.get("verified", 0)
        summary = {
            "run": run,
            "label": label,
            "suite": suite,
            "cases": len(cases),
            "raw": sum(c["raw"] for c in cases),
            "v0": sum(c["v0"] for c in cases),
            "verified": verified,
            "verdicts": dict(verdicts),
            "usd": round(usd, 4),
            "usd_per_verified": round(usd / verified, 4) if verified else None,
            "gate_version": Counter(c["gate_version"] for c in cases).most_common(1)[0][0]
            if cases
            else None,
        }
        index.append(summary)
        (SITE / "runs" / f"{run}.json").write_text(
            json.dumps({"summary": summary, "cases": cases}, indent=1)
        )
    (SITE / "index.json").write_text(json.dumps({"runs": index}, indent=1))
    for name, src in (
        ("calibration", RUNS_DIR / "p1_calibration_v3" / "summary.json"),
        ("leaderboard", RUNS_DIR / "leaderboard.json"),
        ("cuda", RUNS_DIR / "p5_cuda" / "verdicts.json"),
        ("leaderboard_arvo", RUNS_DIR / "leaderboard_arvo.json"),
    ):
        if src.exists():
            (SITE / f"{name}.json").write_text(src.read_text())
    # The demo service's recorded results: real verified Juliet runs, served (and labelled
    # "recorded") whenever live runs are off or a cap is hit.
    rec_dir = REPO_ROOT / "service" / "recorded"
    rec_dir.mkdir(parents=True, exist_ok=True)
    juliet = RUNS_DIR / "p2_sandboxes_juliet3"
    for p in sorted(juliet.glob("CWE*.json"))[:5] if juliet.exists() else []:
        c = case_view(json.loads(p.read_text()))
        keep = {k: c[k] for k in ("case", "verdict", "usd", "elapsed_s", "finding", "winner")}
        keep["workers"] = [{"id": w["id"], "verdict": w["verdict"]} for w in c["workers"]]
        keep["source"] = f"runs/{juliet.name}/{p.name}"
        (rec_dir / p.name).write_text(json.dumps(keep, indent=1), encoding="utf-8")
    print(json.dumps(index, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
