#!/usr/bin/env python3
"""Run the adversary (D-0079) against stored candidates; Nemotron 3 Super and Ultra side by side.

scripts/adversary_eval.py open ROOT       open-bugs diffs (+ the csvsplit demo fix)
scripts/adversary_eval.py arvo-dev ROOT   developer fixes of the 24 accepted calibration cases
scripts/adversary_eval.py arvo-win ROOT   the verified-and-correct ARVO r1 winners, developer
                                          fix as reference

-> runs/adversary/<set>/<case>__<cand>.json (inputs as hex, rows, verdict per model) and
   runs/adversary/<set>/summary.json. Model answers are cached per candidate and model, so a
   re-run only repeats the machine part. ROOT is the live checkout. Needs Docker (workerq).
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

from leakproof import adversary as adv
from leakproof import gate_cli as gc
from leakproof import gate_fuzz as gf
from leakproof.cases import load_case
from leakproof.cases.project import ProjectCase
from leakproof.gate import split
from leakproof.llm import CostLedger, LLMClient
from leakproof.results import records, strict
from leakproof.runner import LocalDockerRunner

MODELS = ("super", "ultra")
BUDGET = 1.50

# case dir -> (config, [(id, record:HYP:worker)]); the D-0078 re-gate list plus csvsplit.
OPEN = {
    "berry_544_format": (
        "cases/open_bugs/berry-lang_berry/544_format/leakproof.toml",
        [
            ("H1w0", "runs/open_bugs_fix/project_544_format.json:H1:0"),
            ("H3w2", "runs/open_bugs_fix/project_544_format.json:H3:2"),
            ("H4w3", "runs/open_bugs_fix/project_544_format.json:H4:3"),
        ],
    ),
    "toybox_571": (
        "cases/open_bugs/landley_toybox/571/leakproof.toml",
        [("H2w1", "runs/open_bugs_fix2/project_571.json:H2:1")],
    ),
    "toybox_572": (
        "cases/open_bugs/landley_toybox/572/leakproof.toml",
        [
            ("H2w1", "runs/open_bugs_fix2/project_572.json:H2:1"),
            ("H3w2", "runs/open_bugs_fix2/project_572.json:H3:2"),
            ("H1w0", "runs/open_bugs_fix2/project_572.json:H1:0"),
        ],
    ),
    "jsmn_249": (
        "cases/open_bugs/zserge_jsmn/leakproof.toml",
        [("H2w3", "runs/open_bugs_r2/project_zserge_jsmn.json:H2:3")],
    ),
    "cnbt_28_leak": (
        "cases/open_bugs/chmod222_cNBT/28_leak/leakproof.toml",
        [
            ("H1w0", "runs/open_bugs_r2/project_28_leak.json:H1:0"),
            ("H1w1", "runs/open_bugs_r2/project_28_leak.json:H1:1"),
        ],
    ),
    "csvsplit": (
        "examples/csvsplit/leakproof.toml",
        [("winner", "runs/demo_fix/project_csvsplit.json:winner")],
    ),
}


def worker_files(rec_path: Path, hyp: str, idx: str) -> tuple[dict[str, str], str]:
    rec = json.loads(rec_path.read_text())
    if hyp == "winner":
        w = rec["winner"]
        hyp, idx = w["hypothesis_id"], str(w["worker_index"])
    w = next(
        w for w in rec["workers"] if (w["hypothesis_id"], str(w["worker_index"])) == (hyp, idx)
    )
    return w["files"], w["diff"]


def how(case: Any) -> str:
    if case.harness_path:
        return (
            f"A libFuzzer harness ({case.harness_path}) is run with the input file as its only "
            "argument; it passes the file's bytes to the code under test."
        )
    return (
        f"The input is written to /tmp/poc, then this command runs in {case.workdir}:\n"
        f"{case.reproduce_cmd}"
    )


def run_inputs(runner, case, image, inputs, files=None):  # noqa: ANN001, ANN201
    repro = f"{case.harness_path} /tmp/poc" if case.harness_path else case.reproduce_cmd
    names = [i["name"] for i in inputs]
    build = case.gate_build_cmd(files) if files else None
    res = runner.run(
        image,
        adv.run_script(names, repro, build),
        files=gc.files([(i["name"], i["data"]) for i in inputs], repro)
        | ({k: v.encode() for k, v in files.items()} if files else {}),
        env=case.build_env | (getattr(case, "reproduce_env", None) or {}),
        cwd=case.workdir,
        timeout_s=3600,
        network=False,
    )
    sec = split(res.stdout)
    if "build_failed" in sec:
        raise RuntimeError("candidate build failed: " + sec["build_failed"][-500:])
    return gc.Run.parse(sec)


def attack_case(
    runner, client, case, out: Path, cands: list[tuple[str, dict[str, str], str]], ref_files=None
) -> list[dict[str, Any]]:  # noqa: ANN001
    t0 = time.monotonic()
    baseline = case.prepare(runner)
    ref = None
    results = []
    try:
        if ref_files:
            from leakproof.calibrate import build_reference

            ref, err = build_reference(case, runner, baseline, ref_files)
            if ref is None:
                print("reference build failed:", err[-300:], flush=True)
        poc = runner.read(baseline, "/tmp/poc")
        report = case.prep.get("report_tail") or json.dumps(case.finding)[:4000]
        target = (gf._norm(case.finding.get("kind", "")), gf.finding_site(case.finding))
        for cid, files, diff in cands:
            originals = {}
            for p in files:
                try:
                    originals[p] = runner.read(baseline, p).decode("utf-8", "replace")
                except Exception:  # noqa: BLE001 - a new file has no original
                    originals[p] = ""
            text = adv.prompt(report, how(case), poc, originals, files, diff)
            row: dict[str, Any] = {"case": case.id, "candidate": cid, "models": {}}
            inputs = []
            for model in MODELS:
                cache = out / f"{case.id.split(':')[-1].split('/')[-1]}__{cid}__{model}.inputs.json"
                if cache.exists():
                    got = json.loads(cache.read_text())
                    for g in got["inputs"]:
                        g["data"] = bytes.fromhex(g["data"])
                    usd = got["usd"]
                else:
                    got_inputs, usd = adv.attack(client, model, text)
                    got = {"inputs": got_inputs, "usd": usd}
                    cache.write_text(
                        json.dumps(
                            {
                                "usd": usd,
                                "inputs": [i | {"data": i["data"].hex()} for i in got_inputs],
                            },
                            indent=1,
                        )
                    )
                for i in got["inputs"]:
                    inputs.append(i | {"name": f"{model[0]}_{i['name']}", "model": model})
                row["models"][model] = {"usd": usd, "n_inputs": len(got["inputs"])}
            if not inputs:
                row["error"] = "no inputs"
                results.append(row)
                continue
            base = run_inputs(runner, case, baseline, inputs)
            try:
                pat = run_inputs(runner, case, baseline, inputs, files)
            except RuntimeError as e:
                row["error"] = str(e)
                results.append(row)
                continue
            refr = run_inputs(runner, case, ref, inputs) if ref else None
            for model in MODELS:
                keep = {i["name"] for i in inputs if i["model"] == model}

                def sub(r: gc.Run | None, keep=keep) -> gc.Run | None:  # noqa: ANN001
                    if r is None:
                        return None
                    return gc.Run(
                        {k: v for k, v in r.rows.items() if k in keep},
                        {k: v for k, v in r.reports.items() if k in keep},
                    )

                verdict, detail, rows = adv.judge(sub(base), sub(pat), sub(refr), target)
                reasons = {i["name"]: (i["expect"], i["reason"]) for i in inputs}
                for r in rows:
                    r["expect"], r["reason"] = reasons.get(r["input"], ("", ""))
                    r["report"] = pat.reports.get(r["input"], "")[:1500]
                row["models"][model] |= {"verdict": verdict, "detail": detail, "rows": rows}
            row["inputs_hex"] = {i["name"]: i["data"].hex() for i in inputs}
            row["reference"] = bool(ref)
            print(
                case.id,
                cid,
                {m: row["models"][m].get("verdict") for m in MODELS},
                flush=True,
            )
            results.append(row)
    finally:
        if ref is not None:
            runner.remove_image(ref)
        case.cleanup(runner)
    for r in results:
        r["elapsed_case_s"] = round(time.monotonic() - t0, 1)
    return results


def main() -> int:
    which, root = sys.argv[1], Path(sys.argv[2]).resolve()
    only = set(sys.argv[3].split(",")) if len(sys.argv) > 3 else None
    out = root / "runs" / "adversary" / which
    out.mkdir(parents=True, exist_ok=True)
    runner = LocalDockerRunner(memory="6g", cpus=4)
    client = LLMClient(ledger=CostLedger(budget=BUDGET), run_id=f"adversary:{which}")
    summary = []
    jobs: list[tuple[Any, list, Any]] = []
    if which == "open":
        for name, (cfg, cands) in OPEN.items():
            if only and name not in only:
                continue
            case = ProjectCase.load(f"project:{root / cfg}")
            loaded = []
            for cid, src in cands:
                rec, hyp, idx = (
                    src.rsplit(":", 2) if src.count(":") >= 2 else (*src.rsplit(":", 1), "")
                )
                files, diff = worker_files(root / rec, hyp, idx)
                loaded.append((cid, files, diff))
            jobs.append((case, loaded, None))
    else:
        from leakproof.calibrate import dev_fix_candidate

        cal = json.loads((root / "site" / "data" / "calibration.json").read_text())
        accepted = [r["case"] for r in cal["rows"] if r["class"] == "accepted"]
        wins = {r["case"]: r for r in records("p3_arvo27_r1") if strict(r)}
        ids = accepted if which == "arvo-dev" else sorted(wins)
        for cid in ids:
            if only and cid not in only:
                continue
            jobs.append((cid, [], which))
    for case, cands, mode in jobs:
        try:
            if mode is None:
                summary += attack_case(runner, client, case, out, cands)
                continue
            c = load_case(case)
            # The developer's fix comes from the upstream commit (preparation step, network on).
            baseline = c.prepare(runner)
            dev, meta = dev_fix_candidate(c, runner, baseline)
            c.cleanup(runner)
            if dev is None:
                summary.append({"case": case, "error": f"no developer fix: {meta.get('error')}"})
                continue
            if mode == "arvo-dev":
                cands = [("developer", dev["files"], dev.get("diff", ""))]
                summary += attack_case(runner, client, c, out, cands)
            else:
                rec = next(r for r in records("p3_arvo27_r1") if r["case"] == case)
                w = rec["winner"]
                files = next(
                    x["files"]
                    for x in rec["workers"]
                    if (x["hypothesis_id"], x["worker_index"])
                    == (w["hypothesis_id"], w["worker_index"])
                )
                summary += attack_case(
                    runner, client, c, out, [("winner", files, w["diff"])], ref_files=dev["files"]
                )
        except Exception as exc:  # noqa: BLE001 - record and continue with the next case
            summary.append(
                {
                    "case": str(getattr(case, "id", case)),
                    "error": f"{type(exc).__name__}: {exc}"[:1500],
                }
            )
            print("error", case, exc, flush=True)
        (out / "summary.json").write_text(json.dumps(summary, indent=1))
    (out / "summary.json").write_text(json.dumps(summary, indent=1))
    usd = sum(m.get("usd", 0) for s in summary for m in s.get("models", {}).values())
    print(f"done: {len(summary)} candidates, ${usd:.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
