"""`leakproof fix --config leakproof.toml`: the fix loop on your own C/C++ project (P5).

Same pipeline and evidence as the ARVO/Juliet runs: baseline build + reproduction, a Nemotron
plan, parallel workers on branches of one checkpoint, the gate in its own process with the
network off, the audit flag; writes runs/<run-id>/<case>.json and prints the funnel.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from leakproof.config import RUNS_DIR, load_dotenv
from leakproof.fix import case_slug, fix_case
from leakproof.llm import CostLedger, LLMClient
from leakproof.runner import LocalDockerRunner, get_runner


def _fix(args: argparse.Namespace) -> int:
    load_dotenv()
    config = Path(args.config).resolve()
    if not config.exists():
        print(f"no such config: {config}", file=sys.stderr)
        return 2
    run_id = args.run_id or f"project_{time.strftime('%Y%m%d_%H%M%S')}"
    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    runner = (
        LocalDockerRunner(memory="4g", cpus=2)
        if args.runner == "docker"
        else get_runner(args.runner, run_id=run_id)
    )
    client = LLMClient(ledger=CostLedger(budget=args.budget), run_id=f"{run_id}:project")
    rec = fix_case(
        f"project:{config}",
        run_dir,
        client,
        runner,
        planner_model=None if args.planner == "none" else args.planner,
        n_workers=args.workers,
    )
    workers = rec.get("workers", [])
    print(f"\nverdict: {rec['verdict']}   ${rec.get('usd', 0):.4f}   {rec.get('elapsed_s')} s")
    if rec.get("error"):
        print(rec["error"][:1500])
    for w in workers:
        flags = ",".join((w.get("audit") or {}).get("flags", [])) or "-"
        print(f"  {w['hypothesis_id']} w{w['worker_index']}: {w['verdict']:<36} reviewer notes: {flags}")
    if rec.get("winner"):
        print("\nwinning diff:\n" + rec["winner"]["diff"])
    print(f"\nrecord: {run_dir / (case_slug(rec['case']) + '.json')}")
    if args.json:
        print(json.dumps(rec, indent=1))
    return 0 if rec["verdict"] == "verified" else 1


MARK = "@@LPBATCH@@"


def _run_inputs(runner, image, case, names: list[str], inputs: dict[str, bytes]) -> dict[str, str]:  # noqa: ANN001
    """Every input through the case's harness on `image`: {name: sanitizer output}."""
    h = case.harness_path
    script = "\n".join(
        f"timeout 60 {h} -timeout=25 -rss_limit_mb=2560 /tmp/lp_in/{n} > /dev/null 2> /tmp/e; "
        f"printf '\\n{MARK} {n}\\n'; tail -c 6000 /tmp/e"
        for n in names
    )
    res = runner.run(
        image,
        script,
        files={f"/tmp/lp_in/{n}": inputs[n] for n in names},
        env=case.build_env | case.reproduce_env,
        cwd=case.workdir,
        timeout_s=3600,
        network=False,
    )
    parts = res.stdout.split(f"\n{MARK} ")
    return {p.split("\n", 1)[0]: (p.split("\n", 1) + [""])[1] for p in parts[1:]}


def _batch(args: argparse.Namespace) -> int:
    """Triage at scale (D-0064): cluster many crash inputs, fix one per cluster, re-check all."""
    from leakproof.cases.project import ProjectCase
    from leakproof.triage import cluster

    load_dotenv()
    config = Path(args.config).resolve()
    found = sorted(p for p in Path(args.findings).iterdir() if p.is_file())
    if not found:
        print(f"no inputs in {args.findings}", file=sys.stderr)
        return 2
    inputs = {p.name: p.read_bytes() for p in found}
    run_id = args.run_id or f"batch_{time.strftime('%Y%m%d_%H%M%S')}"
    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    runner = (
        LocalDockerRunner(memory="4g", cpus=2)
        if args.runner == "docker"
        else get_runner(args.runner, run_id=run_id)
    )
    t0 = time.monotonic()
    # 1. Reproduce every input on one baseline build and cluster by signature.
    seed = ProjectCase.load(f"project:{config}#poc={found[0]}")
    if seed.harness_path is None:
        print("batch mode needs a libFuzzer `harness` in leakproof.toml", file=sys.stderr)
        return 2
    baseline = seed.prepare(runner)
    try:
        reports = _run_inputs(runner, baseline, seed, list(inputs), inputs)
    finally:
        seed.cleanup(runner)
    clusters, clean = cluster(reports, {n: len(b) for n, b in inputs.items()}, seed.src_root)
    print(f"{len(inputs)} inputs -> {len(clusters)} cluster(s); {len(clean)} do not crash")
    rows = []
    # 2. One fix per cluster, then every member's input against the winning patch.
    for i, c in enumerate(clusters, 1):
        rep = Path(args.findings).resolve() / c.representative
        case_id = f"project:{config}#poc={rep}"
        client = LLMClient(ledger=CostLedger(budget=args.budget), run_id=f"{run_id}:c{i}")
        rec = fix_case(case_id, run_dir, client, runner, n_workers=args.workers)
        check = None
        if rec["verdict"] == "verified":
            case = ProjectCase.load(case_id)
            base = case.prepare(runner)
            files = _winner_files(rec)
            try:
                patched = runner.run(
                    base,
                    case.gate_build_cmd(files),
                    files={k: v.encode() for k, v in files.items()},
                    env=case.build_env,
                    cwd=case.workdir,
                    timeout_s=1800,
                    network=False,
                    save=True,
                )
                after = (
                    _run_inputs(runner, patched.image, case, c.members, inputs)
                    if patched.image
                    else {}
                )
                still = [m for m in c.members if "ERROR: " in after.get(m, "ERROR: missing")]
                check = {"members": len(c.members), "still_crash": still}
                if patched.image is not None:
                    runner.remove_image(patched.image)
            finally:
                case.cleanup(runner)
        rows.append(
            {
                "cluster": i,
                "signature": list(c.signature),
                "members": len(c.members),
                "representative": c.representative,
                "verdict": rec["verdict"],
                "verified_for_all_members": bool(check and not check["still_crash"]),
                "member_check": check,
                "usd": rec.get("usd", 0.0),
                "record": f"{case_slug(case_id)}.json",
            }
        )
        print(
            f"  cluster {i} ({len(c.members)} inputs, {' / '.join(c.signature)}): {rec['verdict']}"
            + (f", all members clean: {not check['still_crash']}" if check else "")
        )
    summary = {
        "run_id": run_id,
        "inputs": len(inputs),
        "clusters": len(clusters),
        "not_crashing": clean,
        "verified_clusters": sum(r["verified_for_all_members"] for r in rows),
        "usd": round(sum(r["usd"] for r in rows), 6),
        "wall_s": round(time.monotonic() - t0, 1),
        "rows": rows,
    }
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=1))
    print(
        f"\n{summary['verified_clusters']}/{len(clusters)} clusters verified for every member input; "
        f"${summary['usd']:.4f}; {summary['wall_s']} s; summary: {run_dir / 'summary.json'}"
    )
    return 0


def _winner_files(rec: dict) -> dict[str, str]:
    w = rec["winner"]
    for worker in rec.get("workers", []):
        if (worker["hypothesis_id"], worker["worker_index"], worker.get("round", 1)) == (
            w["hypothesis_id"],
            w["worker_index"],
            w.get("round", 1),
        ):
            return worker["files"]
    return {}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="leakproof")
    sub = ap.add_subparsers(dest="cmd", required=True)
    fx = sub.add_parser("fix", help="fix the memory defect your `reproduce` command trips")
    fx.add_argument("--config", default="leakproof.toml")
    fx.add_argument("--runner", default="docker", choices=["docker", "sandboxes"])
    fx.add_argument("--planner", default="ultra", choices=["ultra", "super", "none"])
    fx.add_argument("--workers", type=int, default=4)
    fx.add_argument("--budget", type=float, default=0.5, help="USD cap for this run")
    fx.add_argument("--run-id")
    fx.add_argument("--json", action="store_true", help="also print the full record")
    bt = sub.add_parser("batch", help="triage many crash inputs: cluster, fix once each, re-check")
    bt.add_argument("--config", default="leakproof.toml")
    bt.add_argument("--findings", required=True, help="directory of crash inputs")
    bt.add_argument("--runner", default="docker", choices=["docker", "sandboxes"])
    bt.add_argument("--workers", type=int, default=4)
    bt.add_argument("--budget", type=float, default=0.5, help="USD cap per cluster")
    bt.add_argument("--run-id")
    args = ap.parse_args(argv)
    return _batch(args) if args.cmd == "batch" else _fix(args)


if __name__ == "__main__":
    sys.exit(main())
