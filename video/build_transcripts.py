#!/usr/bin/env python3
"""Terminal transcripts for the video draft, rebuilt from recorded runs (no new model calls).

video/build_transcripts.py -> video/transcripts/*.txt

Each transcript is what the CLI printed (or prints) for a recorded run: the csvsplit crash from
the baseline report, `leakproof fix` from runs/demo_fix, `leakproof batch` from runs/demo_batch,
and the jq evidence bundle. The first line of each says it is a replay of a recorded run.
"""

from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from leakproof.config import RUNS_DIR  # noqa: E402
from leakproof.evidence import explain, strength  # noqa: E402

OUT = ROOT / "video" / "transcripts"


def crash() -> str:
    rec = json.loads((RUNS_DIR / "demo_fix" / "project_csvsplit.json").read_text())
    tail = rec["project"]["prep"]["report_tail"]
    start = tail.find("==ERROR")
    report = tail[start:].splitlines() if start >= 0 else tail.splitlines()
    keep = [ln for ln in report if ln.strip() and not ln.lstrip().startswith("0x")]
    # The sanitizer header and the project's own frames; libFuzzer's frames add nothing here.
    keep = [
        ln
        for ln in keep
        if "fuzzer::" not in ln
        and "libc_start" not in ln
        and " in main " not in ln
        and " in _start " not in ln
    ][:5]
    return "\n".join(
        [
            "# replay of a recorded run: runs/demo_fix (2026-10-24)",
            "$ ./csvsplit_fuzz poc.csv",
            *keep,
        ]
    )


def fix() -> tuple[str, str]:
    """Two scenes: the plan, workers and verdict together; then the winning diff."""
    rec = json.loads((RUNS_DIR / "demo_fix" / "project_csvsplit.json").read_text())
    plan = textwrap.wrap(rec["plan"]["root_cause"], 100)
    if len(plan) > 3:
        plan = plan[:3]
        plan[2] = plan[2][:97] + "..."
    lines = [
        "# replay of a recorded run: runs/demo_fix (2026-10-24)",
        "$ uv run leakproof fix --config examples/csvsplit/leakproof.toml",
        "plan (Nemotron 3 Ultra):",
        *(f"  {ln}" for ln in plan),
        f"{rec['n_workers']} workers (Nemotron 3.5 Lightning) -> gate (own process, network off)",
        "",
        f"verdict: {rec['verdict']}   ${rec['usd']:.4f}   {rec['elapsed_s']} s",
    ]
    for w in rec["workers"]:
        lines.append(f"  {w['hypothesis_id']} w{w['worker_index']}: {w['verdict']}")
    win = next(w for w in rec["workers"] if w["diff"] == rec["winner"]["diff"])
    corpus = (rec.get("gate") or {}).get("corpus") or {}
    ev = strength(win["gate"]["checks"], corpus if "stdout_distinct" in corpus else None)
    lines += ["", f"{ev['label'].upper()}: {explain(ev)}"]
    diff = [
        "# replay of a recorded run: runs/demo_fix (2026-10-24)",
        "winning diff (src/csvsplit.c):",
        *(
            ln
            for ln in rec["winner"]["diff"].rstrip().splitlines()
            if not ln.startswith(("---", "+++"))
        ),
    ]
    return "\n".join(lines), "\n".join(diff)


def batch() -> str:
    s = json.loads((RUNS_DIR / "demo_batch" / "summary.json").read_text())
    lines = [
        "# replay of a recorded run: runs/demo_batch (2026-10-24)",
        "$ uv run leakproof batch --config examples/csvsplit/leakproof.toml "
        "--findings examples/csvsplit/findings",
        f"{s['inputs']} inputs -> {s['clusters']} cluster(s); "
        f"{len(s['not_crashing'])} do not crash",
    ]
    for r in s["rows"]:
        lines.append(
            f"  cluster {r['cluster']} ({r['members']} inputs, {' / '.join(r['signature'])}): "
            f"{r['verdict']}, all members clean: {r['verified_for_all_members']}"
        )
    lines.append(
        f"\n{s['verified_clusters']}/{s['clusters']} clusters verified for every member input; "
        f"${s['usd']:.4f}; {s['wall_s']} s"
    )
    return "\n".join(lines)


def jq() -> str:
    bundle = (ROOT / "docs" / "bundles" / "42530604.md").read_text(encoding="utf-8")
    return "\n".join(
        [
            "# evidence bundle of a recorded run: runs/p3_arvo27_r1",
            "$ head docs/bundles/42530604.md",
        ]
        + bundle.replace("**", "").replace("`", "").splitlines()[:9]
    )


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, text in (
        ("01_jq_bundle", jq()),
        ("03_crash", crash()),
        ("04_fix", fix()[0]),
        ("05_fix_diff", fix()[1]),
        ("07_batch", batch()),
    ):
        (OUT / f"{name}.txt").write_text(text + "\n", encoding="utf-8", newline="\n")
        print(f"== {name}\n{text}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
