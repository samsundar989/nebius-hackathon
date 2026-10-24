#!/usr/bin/env python3
"""Planner root-cause accuracy against the developers' fixes (strategist order C1), a proxy.

  scripts/root_cause_accuracy.py p3_arvo27_r1      -> runs/<run>/root_cause_accuracy.json

Per ARVO case with a plan and a developer-fix reference:
  file match      a hypothesis names a file the developer's fix changed
  function match  the root cause names a function the developer's fix changed (from the fix
                  commit's hunk headers: the function enclosing each change's first line, so a
                  noisy lower bound; cases whose hunks name no function are not counted)
"""

from __future__ import annotations

import json
import re
import sys

from leakproof.calibrate import fetch_patch, fix_commits
from leakproof.config import RUNS_DIR

KEYWORDS = {"if", "for", "while", "switch", "sizeof", "return"}


def changed_functions(case_id: str, commits: list[str], files: list[str], project: str) -> set:
    repo, sets = fix_commits(case_id)
    funcs: set[str] = set()
    rels = [f.split(f"/src/{project}/")[-1] for f in files]
    for sha in commits or (sets[0] if sets else []):
        try:
            text = fetch_patch(repo, sha)
        except OSError:
            continue
        cur = None
        for line in text.splitlines():
            if line.startswith("+++ b/"):
                cur = line[6:]
            m = re.match(r"^@@ [^@]+ @@\s*(.*)", line)
            if m and cur and any(cur.endswith(r) for r in rels):
                funcs |= {f for f in re.findall(r"(\w+)\s*\(", m.group(1)) if f not in KEYWORDS}
    return funcs


def main(argv: list[str]) -> int:
    run = RUNS_DIR / argv[0]
    rows = []
    for path in sorted(run.glob("*.json")):
        if path.name in ("summary.json", "root_cause_accuracy.json"):
            continue
        rec = json.loads(path.read_text())
        ref, plan, arvo = rec.get("reference") or {}, rec.get("plan") or {}, rec.get("arvo") or {}
        if not ref.get("files") or not plan.get("root_cause"):
            continue
        funcs = changed_functions(rec["case"], ref.get("commits"), ref["files"], arvo["project"])
        dev = {p.rsplit("/", 1)[-1] for p in ref["files"]}
        hyp = {p.rsplit("/", 1)[-1] for h in plan["hypotheses"] for p in h.get("files", [])}
        rows.append(
            {
                "case": rec["case"],
                "project": arvo.get("project"),
                "verdict": rec["verdict"],
                "file_match": bool(dev & hyp),
                "function_match": any(
                    re.search(rf"\b{re.escape(f)}\b", plan["root_cause"]) for f in funcs
                )
                if funcs
                else None,
                "developer_functions": sorted(funcs),
            }
        )
    fm = [r for r in rows if r["function_match"] is not None]
    out = {
        "run": argv[0],
        "cases": len(rows),
        "file_match": sum(r["file_match"] for r in rows),
        "function_match": sum(bool(r["function_match"]) for r in fm),
        "function_cases": len(fm),
        "rows": rows,
    }
    (run / "root_cause_accuracy.json").write_text(json.dumps(out, indent=1))
    print(
        f"{argv[0]}: file match {out['file_match']}/{out['cases']}, function match "
        f"{out['function_match']}/{out['function_cases']} (proxy, see docstring)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
