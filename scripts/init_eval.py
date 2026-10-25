#!/usr/bin/env python3
"""Measure `leakproof init` on the hand-configured open-bugs projects (review #8 order 4).

scripts/init_eval.py draft ROOT   -> runs/init_eval/<case>/{issue.json,leakproof.toml,poc*}
scripts/init_eval.py check ROOT   -> runs/init_eval/results.json (needs Docker: workerq)

`draft` reads each issue text in runs/init_eval/issues/ with Nemotron Nano (once; issue.json is
reused) and writes the draft config next to it. `check` prepares every draft's baseline: does the
draft build unchanged, and does its reproducer trip a sanitizer? ROOT is the live checkout (the
upstream clones are not in workerq's snapshot).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from leakproof import init
from leakproof.cases.project import ProjectCase
from leakproof.llm import CostLedger, LLMClient
from leakproof.runner import LocalDockerRunner


def draft(root: Path) -> None:
    ev = root / "runs" / "init_eval"
    client = LLMClient(ledger=CostLedger(budget=0.30), run_id="init_eval")
    for issue_md in sorted((ev / "issues").glob("*.md")):
        case = issue_md.stem
        repo = root / "cases" / "open_bugs" / case.rsplit("_", 1)[0] / "src"
        out = ev / case
        out.mkdir(parents=True, exist_ok=True)
        cached = out / "issue.json"
        if cached.exists():
            issue = json.loads(cached.read_text())
        else:
            issue, usd = init.from_issue(client, issue_md.read_text(encoding="utf-8"))
            cached.write_text(json.dumps(issue, indent=1))
            print(f"{case}: Nano ${usd:.4f}")
        for old in out.glob("poc*"):
            old.unlink()
        src = os.path.relpath(repo, out).replace(os.sep, "/")
        text = init.draft(repo, issue, name=case, src=src)
        (out / "leakproof.toml").write_text(text, encoding="utf-8", newline="\n")
        init.write_poc(out, issue)
        print(f"== {case}\n{text}")


def check(root: Path) -> None:
    ev = root / "runs" / "init_eval"
    runner = LocalDockerRunner(memory="4g", cpus=2)
    results = {}
    for cfg in sorted(ev.glob("*/leakproof.toml")):
        case = cfg.parent.name
        text = cfg.read_text(encoding="utf-8")
        row: dict = {
            "build_cmd": "TODO build" not in text,
            "reproduce_cmd": "TODO reproduce" not in text,
        }
        if not row["build_cmd"]:
            results[case] = row | {"outcome": "no build system detected"}
            continue
        if not row["reproduce_cmd"]:
            # Build only: a reproducer that cannot fail stands in for the missing one.
            text = text.replace(
                "# TODO reproduce = '''./your-binary /tmp/poc'''  # must trip a sanitizer",
                "reproduce = '''true'''",
            )
            cfg = cfg.with_name("leakproof.build_only.toml")
            cfg.write_text(text, encoding="utf-8", newline="\n")
        pc = ProjectCase.load(f"project:{cfg.resolve()}")
        try:
            pc.prepare(runner)
            row["outcome"] = "builds and reproduces"
            row["finding"] = pc.finding
        except RuntimeError as e:
            msg = str(e)
            row["outcome"] = (
                "build failed"
                if "build failed" in msg
                else "builds; reproducer missing"
                if not row["reproduce_cmd"]
                else "builds; reproducer does not trip a sanitizer"
            )
            row["detail"] = msg[-1200:]
        finally:
            pc.cleanup(runner)
        results[case] = row
        print(case, row["outcome"], flush=True)
    (ev / "results.json").write_text(json.dumps(results, indent=1))


if __name__ == "__main__":
    {"draft": draft, "check": check}[sys.argv[1]](Path(sys.argv[2]).resolve())
