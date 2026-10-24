"""One case end to end: baseline -> plan -> parallel workers -> gate (subprocess) -> funnel JSON."""

from __future__ import annotations

import json
import subprocess
import sys
import time
import traceback
from collections.abc import Callable
from pathlib import Path
from typing import Any

from leakproof.audit import audit
from leakproof.branch import fan_out
from leakproof.cases import load_case
from leakproof.config import REPO_ROOT
from leakproof.llm import LLMClient
from leakproof.planner import no_planner_hypotheses, plan
from leakproof.runner import ImageRef, Runner

# Juliet keeps the kickoff's 6K. Real files are 1-3K lines and Lightning's reasoning ran into
# 6K mid-fix on 3/4 ARVO workers (mosquitto 42520955, E1 run 1), hence 12K there (D-0040).
WORKER_MAX_TOKENS = {"juliet": 6_000, "arvo": 12_000, "project": 12_000}

# Best outcome first; a case's verdict is its best candidate's.
VERDICT_RANK = [
    "verified",
    "silenced_only",
    "rejected",
    "build_failed",
    "no_candidate",
    "inconclusive",
    "error",
]


def case_slug(case_id: str) -> str:
    """File-system name for a case: `project:<path>/leakproof.toml` -> `project_<dir>`."""
    if case_id.startswith("project:"):
        return "project_" + Path(case_id.removeprefix("project:")).resolve().parent.name
    return case_id


def rank(verdict: str) -> int:
    head = verdict.split(":", 1)[0]
    return VERDICT_RANK.index(head) if head in VERDICT_RANK else len(VERDICT_RANK)


def run_gate_process(
    case_id: str,
    baseline: str,
    workdir: str | None,
    finding: dict[str, Any],
    candidates: list[dict[str, Any]],
    case_dir: Path,
    reference: str | None = None,
    runner_name: str = "docker",
) -> dict[str, Any]:
    cpath, vpath = case_dir / "candidates.json", case_dir / "gate.json"
    cpath.write_text(json.dumps({"finding": finding, "candidates": candidates}, indent=1))
    cmd = [
        sys.executable,
        "-m",
        "leakproof.gate",
        "--case",
        case_id,
        "--baseline",
        baseline,
        "--candidates",
        str(cpath),
        "--out",
        str(vpath),
    ]
    if workdir:
        cmd += ["--workdir", workdir]
    if reference:
        cmd += ["--reference", reference]
    if runner_name != "docker":
        cmd += ["--runner", runner_name]
    proc = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True, check=False)
    if proc.returncode != 0 or not vpath.exists():
        raise RuntimeError(f"gate process failed ({proc.returncode}): {proc.stderr[-2000:]}")
    return json.loads(vpath.read_text())


def fix_case(
    case_id: str,
    run_dir: Path,
    client: LLMClient,
    runner: Runner,
    *,
    planner_model: str | None = "ultra",
    worker_model: str = "lightning",
    n_workers: int = 4,
    worker_max_tokens: int | None = None,
    audit_model: str | None = "lightning",
    reference_builder: Callable[[Any, Runner, Any], tuple[str | None, Any]] | None = None,
) -> dict[str, Any]:
    """`client` must be this case's own (its ledger's spend is the case's cost).

    reference_builder(case, runner, baseline) -> (image ref or None, record): supplied by a
    gate-side script (calibration, ARVO batch); called after the workers, before the gate.
    """
    reference: str | None = None
    t0 = time.monotonic()
    case_dir = run_dir / case_slug(case_id)
    case_dir.mkdir(parents=True, exist_ok=True)
    spent0 = client.ledger.spent
    rec: dict[str, Any] = {
        "case": case_id,
        "planner_model": planner_model,
        "worker_model": worker_model,
        "n_workers": n_workers,
        "started": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    case = load_case(case_id)
    rec["suite"] = case.suite
    if case.suite == "juliet" and not case.finding:
        # E0 could not reproduce it (D-0021); it stays in the denominator, unattempted.
        rec.update(
            verdict="inconclusive:not_reproducible",
            usd=0.0,
            usd_by_model={},
            note=case.data.get("not_reproducible_reason"),
            elapsed_s=round(time.monotonic() - t0, 2),
        )
        (run_dir / f"{case_slug(case_id)}.json").write_text(json.dumps(rec, indent=1))
        return rec
    gate: dict[str, Any] | None = None
    try:
        p0 = time.monotonic()
        baseline = case.prepare(runner)
        rec["baseline"] = {"image": baseline.ref, "prepare_s": round(time.monotonic() - p0, 2)}
        if case.suite in ("arvo", "project"):
            rec[case.suite] = case.record()
        rec["finding"] = case.finding
        sources = case.visible_sources(runner)
        windows = case.windows(runner)
        rec["files_shown"] = sorted(sources)
        if planner_model:
            pl = plan(
                client,
                case.finding,
                windows,
                sorted(sources),
                case.build_description(),
                model=planner_model,
            )
            rec["plan"] = pl.to_dict()
            root_cause = pl.root_cause
            # Fewer hypotheses than workers: cycle them (sampling at temperature > 0 varies
            # the edits); a single worker's formatting slip should not sink the case.
            hyps = [pl.hypotheses[i % len(pl.hypotheses)] for i in range(n_workers)]
        else:
            root_cause = "(no planner)"
            hyps = no_planner_hypotheses(case.finding, sorted(sources), n_workers)
            rec["plan"] = {"root_cause": root_cause, "hypotheses": hyps, "model": None, "usd": 0.0}
        cands = fan_out(
            client,
            runner,
            case,
            baseline,
            root_cause=root_cause,
            hypotheses=hyps,
            sources=sources,
            windows=windows,
            model=worker_model,
            max_completion_tokens=worker_max_tokens or WORKER_MAX_TOKENS[case.suite],
        )
        strategy = {h["id"]: h["strategy"] for h in hyps}
        # Identical patches are gated once.
        unique: dict[str, dict[str, Any]] = {}
        for c in cands:
            if c.status == "built" and c.diff not in unique:
                unique[c.diff] = {
                    "hypothesis_id": c.hypothesis_id,
                    "worker_index": c.worker_index,
                    "strategy": strategy.get(c.hypothesis_id, "other"),
                    "files": c.files,
                    "diff": c.diff,
                }
        if unique and reference_builder is not None:
            # Only now, with every candidate final: the gate side builds its reference (the
            # developer's fix) for attribution. Workers have finished and never see it.
            reference, rec["reference"] = reference_builder(case, runner, baseline)
        if unique:
            gate = run_gate_process(
                case_id,
                baseline.ref,
                getattr(case, "workdir", None),
                case.finding,
                list(unique.values()),
                case_dir,
                reference=reference,
                runner_name=getattr(runner, "name", "docker"),
            )
            rec["gate"] = {k: v for k, v in gate.items() if k != "results"}
        by_diff = {}
        if gate:
            for g, u in zip(gate["results"], unique.values(), strict=True):
                by_diff[u["diff"]] = g
        # Check 8: flags only, after the verdicts exist and never feeding back into them.
        audits = (
            {d: audit(client, case.finding, d, model=audit_model) for d in unique}
            if audit_model
            else {}
        )
        workers = []
        for c in cands:
            w = c.to_dict()
            if c.status == "built":
                g = by_diff[c.diff]
                w["gate"] = g
                w["verdict"] = g["verdict"]
                if c.diff in audits:
                    w["audit"] = audits[c.diff]
            elif c.status == "build_failed":
                w["verdict"] = "build_failed"
            elif c.status == "error":
                w["verdict"] = f"error:{(c.error or '')[:80]}"
            else:
                w["verdict"] = f"no_candidate:{c.status}"
            workers.append(w)
        rec["workers"] = workers
        best = min(
            workers, key=lambda w: (rank(w["verdict"]), len(w["diff"]) or 10**9), default=None
        )
        rec["verdict"] = best["verdict"] if best else "no_candidate"
        rec["winner"] = (
            {
                "hypothesis_id": best["hypothesis_id"],
                "worker_index": best["worker_index"],
                "diff": best["diff"],
            }
            if best and best["verdict"] == "verified"
            else None
        )
        if case.suite == "juliet" and not getattr(case, "reproducible", True):
            rec["note"] = "case marked not reproducible in E0 (D-0021); kept in the denominator"
    except Exception as exc:
        rec["verdict"] = f"error:{type(exc).__name__}"
        rec["error"] = f"{exc}\n{traceback.format_exc()[-3000:]}"
    finally:
        try:
            if reference and hasattr(runner, "remove_image"):
                runner.remove_image(ImageRef(getattr(runner, "name", "docker"), reference))
            case.cleanup(runner)
        except Exception as exc:  # noqa: BLE001 - cleanup must not mask the result
            rec["cleanup_error"] = str(exc)
    if getattr(runner, "lineage", None) is not None:
        # Worker side (baseline + branch builds); the gate's own runs are in gate.json.
        rec["lineage"] = {
            "workers": runner.lineage,
            "gate": (gate or {}).get("lineage"),
        }
    rec["usd"] = round(client.ledger.spent - spent0, 6)
    rec["usd_by_model"] = {m: round(v, 6) for m, v in client.ledger.by_model.items()}
    rec["elapsed_s"] = round(time.monotonic() - t0, 2)
    (run_dir / f"{case_slug(case_id)}.json").write_text(json.dumps(rec, indent=1))
    return rec
