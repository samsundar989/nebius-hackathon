#!/usr/bin/env python3
"""Evidence bundle per case: a PR-style markdown page from a fix_case record (P5.2).

  scripts/render_bundle.py p3_arvo27_r1 [--all] [--out docs/bundles]

Verified cases by default (--all: every case). Each bundle: summary, root cause, the winning
diff, the gate matrix with every check's evidence, before/after sanitizer reports, the funnel
over all workers (verdict + advisory reviewer notes), cost by model, and the developer's fix for comparison.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from leakproof.config import REPO_ROOT, RUNS_DIR

CHECK_ORDER = [
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
ICON = {"pass": "pass", "fail": "**fail**", "skipped": "skipped", "inconclusive": "inconclusive"}


def _fence(text: str, lang: str = "") -> str:
    text = text.strip("\n")
    fence = "````" if "```" in text else "```"
    return f"{fence}{lang}\n{text}\n{fence}"


def _one_line(text: str, n: int = 220) -> str:
    return re.sub(r"\s+", " ", text or "").strip()[:n]


def bundle(rec: dict, case_dir: Path) -> str:
    case = rec["case"]
    arvo = rec.get("arvo") or {}
    finding = rec.get("finding") or {}
    plan = rec.get("plan") or {}
    workers = rec.get("workers", [])
    gated = [w for w in workers if w.get("gate")]
    winner = rec.get("winner")
    win = next(
        (
            w
            for w in gated
            if winner
            and w["hypothesis_id"] == winner["hypothesis_id"]
            and w["worker_index"] == winner["worker_index"]
        ),
        None,
    )
    title = arvo.get("project") or rec.get("suite", "")
    out = [f"# {title} {case}: {rec['verdict']}", ""]
    if rec["verdict"] != "verified":
        # Refused cases lead with why (strategist order D): the first failed check of each
        # distinct gated candidate, or what stopped the workers before the gate.
        why = []
        for w in gated:
            failed = [
                (k, v)
                for k, v in w["gate"]["checks"].items()
                if v["status"] in ("fail", "inconclusive")
            ]
            if failed:
                k, v = failed[0]
                why.append(f"w{w['worker_index']} {k}: {_one_line(v['detail'], 160)}")
        if not why:
            why = sorted({w["verdict"] for w in workers}) or [
                rec.get("error", "no candidate")[:160]
            ]
        out += [f"**Not fixed — no candidate passed the gate.** {'; '.join(why[:3])}", ""]
    out += [
        f"- **Defect:** {finding.get('kind', '?')} at `{finding.get('location', '?')}`"
        + (f" (ARVO crash type: {arvo['crash_type']})" if arvo.get("crash_type") else ""),
        f"- **Models:** planner `{rec.get('planner_model')}`, {rec.get('n_workers')} x "
        f"`{rec.get('worker_model')}` workers; reviewer notes `lightning` (advisory, D-0060)",
        f"- **Cost:** ${rec.get('usd', 0):.4f} "
        + " · ".join(
            f"{m.split('/')[-1]} ${v:.4f}" for m, v in rec.get("usd_by_model", {}).items()
        ),
        f"- **Wall time:** {rec.get('elapsed_s')} s",
    ]
    if arvo.get("patch_url"):
        out.append(f"- **Developer's fix (for comparison):** {arvo['patch_url']}")
    out += ["", "## Root cause (planner)", "", plan.get("root_cause", "(no planner)"), ""]
    if winner:
        out += ["## The fix", "", _fence(winner["diff"], "diff"), ""]
    if win:
        out += ["## Gate evidence", "", "| check | result | evidence |", "|---|---|---|"]
        checks = win["gate"]["checks"]
        for name in CHECK_ORDER + [k for k in checks if k not in CHECK_ORDER]:
            if name in checks:
                c = checks[name]
                out.append(
                    f"| {name} | {ICON.get(c['status'], c['status'])} | "
                    f"{_one_line(c['detail']).replace('|', '/')} |"
                )
        before = (arvo.get("prep") or {}).get("report_tail") or ""
        if before:
            out += ["", "### Before: sanitizer report on the unpatched build", ""]
            out.append(_fence(before[-2500:]))
        ev = win["gate"].get("evidence") or {}
        out += [
            "",
            "### After",
            "",
            f"PoC on the patched build: {checks.get('patched', {}).get('detail', '?')}; "
            f"PoC under LeakSanitizer: {ev.get('poc_under_lsan', 'n/a')}.",
        ]
        amp = win["gate"].get("amplification") or {}
        if amp:
            clean = sum(1 for v in amp.values() if v["rc"] == "0" and not v["sig"])
            out.append(f"Amplified PoC variants: {clean}/{len(amp)} clean ({', '.join(amp)}).")
        if win.get("audit", {}).get("flags"):
            out += ["", "### Reviewer notes (an LLM review; advisory, never gating, D-0060)", ""]
            for k in win["audit"]["flags"]:
                out.append(f"- `{k}`: {win['audit']['checks'][k]['note']}")
    out += [
        "",
        "## Funnel: every worker",
        "",
        "| worker | hypothesis | verdict | reviewer notes |",
        "|---|---|---|---|",
    ]
    for w in workers:
        flags = ", ".join((w.get("audit") or {}).get("flags", [])) or "-"
        out.append(f"| w{w['worker_index']} | {w['hypothesis_id']} | {w['verdict']} | {flags} |")
    rejected = [w for w in gated if w["verdict"].startswith("rejected")]
    if rejected:
        out += ["", "### Why the rejected candidates were rejected", ""]
        for w in rejected:
            failed = {k: v for k, v in w["gate"]["checks"].items() if v["status"] == "fail"}
            for k, v in failed.items():
                out.append(f"- w{w['worker_index']} `{k}`: {_one_line(v['detail'], 300)}")
    out += [
        "",
        "---",
        f"Generated by `scripts/render_bundle.py` from `runs/{case_dir.parent.name}/"
        f"{case_dir.name}.json`. The gate ran in its own process with the network off; workers "
        "never saw its corpus, fuzzing settings or the developer's fix.",
    ]
    return "\n".join(out) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--out", type=Path, default=REPO_ROOT / "docs" / "bundles")
    args = ap.parse_args()
    run_dir = RUNS_DIR / args.run
    args.out.mkdir(parents=True, exist_ok=True)
    n = 0
    for path in sorted(run_dir.glob("*.json")):
        if path.name == "summary.json":
            continue
        rec = json.loads(path.read_text())
        if not args.all and rec.get("verdict") != "verified":
            continue
        (args.out / f"{path.stem}.md").write_text(
            bundle(rec, run_dir / path.stem), encoding="utf-8", newline="\n"
        )
        n += 1
    print(f"wrote {n} bundle(s) to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
