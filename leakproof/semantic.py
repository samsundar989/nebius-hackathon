"""Semantic audit (D-0069): is a verified fix *correct*, judged against the developer's fix.

The gate shows a candidate is safe on every input it tried; it cannot see behaviour the harness
does not print (mosquitto 42520955: the default listener's settings land on the wrong listener).
Nemotron 3 Ultra compares each verified diff with the upstream fix and gives one class. Advisory
only: the result is adjudicated by hand (cases/arvo/semantic_adjudication.json) and never feeds a
gate verdict. Runs after the fact on stored records; no worker sees it.
"""

from __future__ import annotations

import difflib
import json
import re
from pathlib import Path
from typing import Any

from leakproof.config import RUNS_DIR
from leakproof.llm import LLMClient

CLASSES = ("equivalent", "different_but_correct", "defensive", "wrong", "unsure")
CORRECT = ("equivalent", "different_but_correct")
SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "class": {"type": "string", "enum": list(CLASSES)},
        "reason": {"type": "string"},
    },
    "required": ["class", "reason"],
    "additionalProperties": False,
}
SYSTEM = (
    "You compare two patches for the same memory-safety defect in C/C++: the upstream "
    "developer's fix and a candidate fix. Both already stop the crash and pass sanitizer "
    "checks. Decide whether the candidate is semantically correct. Classes:\n"
    "- equivalent: same root-cause fix as the developer's, possibly written differently.\n"
    "- different_but_correct: fixes the root cause another way, with behaviour on valid "
    "inputs a maintainer would accept.\n"
    "- defensive: safe, but guards the symptom (a clamp, bounds check or early return at the "
    "consumer) instead of fixing the cause the developer fixed.\n"
    "- wrong: changes behaviour on valid inputs incorrectly (wrong object, lost data, wrong "
    "result), even though it no longer crashes.\n"
    "- unsure: the context shown is not enough to tell.\n"
    "Give a reason of 2-4 sentences naming the specific lines (file:line) that decide it."
)


def _reverse(new: str, diff_for_file: list[str]) -> str:
    """The original file: undo one file's unified-diff hunks on its patched text."""
    lines = new.splitlines(keepends=True)
    hunks: list[tuple[int, int, list[str]]] = []
    for line in diff_for_file:
        m = re.match(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", line)
        if m:
            hunks.append((int(m.group(1)), int(m.group(2) or 1), []))
        elif hunks and line[:1] in " +-":
            hunks[-1][2].append(line)
    for start, count, body in reversed(hunks):
        old = [x[1:] for x in body if x[:1] in " -"]
        at = start - 1 if count else start
        lines[at : at + count] = old
    return "".join(lines)


def originals(files: dict[str, str], diff: str) -> dict[str, str]:
    """{path: original text} for every file the diff touches, rebuilt from the patched files."""
    per: dict[str, list[str]] = {}
    cur = None
    for line in diff.splitlines(keepends=True):
        if line.startswith("+++ b/"):
            cur = "/" + line[6:].strip()
            per[cur] = []
        elif line.startswith("--- "):
            continue
        elif cur is not None:
            per[cur].append(line)
    return {p: _reverse(files[p], d) for p, d in per.items() if p in files}


def wide_diff(files: dict[str, str], diff: str, context: int = 30) -> str:
    """The same change with `context` lines around each hunk, so the enclosing function shows."""
    out = []
    for path, before in originals(files, diff).items():
        out += difflib.unified_diff(
            before.splitlines(keepends=True),
            files[path].splitlines(keepends=True),
            fromfile=f"a{path}",
            tofile=f"b{path}",
            n=context,
        )
    return "".join(c if c.endswith("\n") else c + "\n" for c in out) or diff


def classify(
    client: LLMClient,
    finding: dict[str, Any],
    root_cause: str,
    developer_diff: str,
    candidate_diff: str,
    *,
    model: str = "ultra",
    max_completion_tokens: int = 12000,
) -> dict[str, Any]:
    frames = " <- ".join(
        f"{f.get('function')} ({(f.get('file') or '?').rsplit('/', 1)[-1]}:{f.get('line')})"
        for f in (finding.get("frames") or [])[:5]
    )
    user = (
        f"Defect: {finding.get('kind', '?')} at {finding.get('location') or '?'}\n"
        f"Stack: {frames}\n"
        f"Planner's root cause (may be wrong): {root_cause[:1500]}\n\n"
        f"Developer's fix:\n{developer_diff[:16000]}\n\n"
        f"Candidate fix:\n{candidate_diff[:16000]}"
    )
    value, res = client.structured(
        model,
        [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
        SCHEMA,
        purpose="semantic_audit",
        thinking=True,
        max_completion_tokens=max_completion_tokens,
    )
    return {"class": value["class"], "reason": value["reason"], "model": res.model, "usd": res.usd}


# ------------------------------------------------------------------------------- records
RUNS = (
    "p3_arvo27_r1",
    "p3_arvo27_r2",
    "lb_arvo_lightning_r1",
    "lb_arvo_super_r1",
    "lb_arvo_ultra_r1",
)
REJUDGED = {"p3_arvo27_r1": RUNS_DIR / "p3_rejudge_d0056"}  # D-0056 re-judge verdicts


def change(diff: str) -> str:
    """A diff reduced to its changed lines: identical edits from different workers dedupe."""
    return "\n".join(
        x for x in diff.splitlines() if x[:1] in "+-" and not x.startswith(("+++", "---"))
    )


def verified_candidates() -> dict[str, dict]:
    """{case: {"finding", "root_cause", "candidates": {change: {"diff", "files", "members"}}}}."""
    cases: dict[str, dict] = {}
    for run in RUNS:
        for p in sorted((RUNS_DIR / run).glob("*.json")):
            if p.name == "summary.json":
                continue
            rec = json.loads(p.read_text())
            workers = list(rec.get("workers", []))
            rejudge = REJUDGED.get(run, Path("-")) / rec["case"] / run
            if rejudge.exists():
                gate = json.loads((rejudge / "gate.json").read_text())
                ok = {
                    (g["hypothesis_id"], g["worker_index"])
                    for g in gate["results"]
                    if g["verdict"] == "verified"
                }
                for w in workers:
                    if (w["hypothesis_id"], w["worker_index"]) in ok:
                        w["verdict"] = "verified"
            c = cases.setdefault(
                rec["case"],
                {
                    "finding": rec["finding"],
                    "root_cause": rec["plan"].get("root_cause", ""),
                    "candidates": {},
                },
            )
            for w in workers:
                if w.get("verdict") != "verified":
                    continue
                cand = c["candidates"].setdefault(
                    change(w["diff"]), {"diff": w["diff"], "files": w["files"], "members": []}
                )
                cand["members"].append(
                    {
                        "run": run,
                        "hypothesis_id": w["hypothesis_id"],
                        "worker_index": w["worker_index"],
                        "round": w.get("round", 1),
                    }
                )
    return cases


def developer(case: str) -> dict | None:
    p = RUNS_DIR / "p1_calibration_v3" / case / "dev" / "candidates.json"
    if not p.exists():
        return None
    return json.loads(p.read_text())["candidates"][0]
