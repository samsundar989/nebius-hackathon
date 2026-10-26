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
import os
import sys
import time
from pathlib import Path
from typing import Any

from leakproof import adversary as adv
from leakproof import gate_cli as gc
from leakproof import gate_fuzz as gf
from leakproof.cases import load_case
from leakproof.cases.project import ProjectCase
from leakproof.llm import CostLedger, LLMClient
from leakproof.results import records, strict
from leakproof.runner import LocalDockerRunner

# variant -> (model, thinking). super_think ran once on the open bugs (prompt v1): it spent its
# 32k-token budget reasoning and cost ~$0.03 a call, so it is not in the default set.
VARIANTS = {
    "super": ("super", False),
    "ultra": ("ultra", False),
    "super_think": ("super", True),
    "super_fb": ("super", False),  # Super, Ultra once on no usable input (D-0080)
}
MODELS = ("super", "ultra")
# Review #10: the adversary overran its $1.50 order cap ($2.44 with three prompt versions and
# repairs); the remaining runs are Super only, $0.40 at most.
BUDGET = float(os.environ.get("LEAKPROOF_ADVERSARY_BUDGET", "0.40"))
ACTIVE = tuple(os.environ.get("LEAKPROOF_ADVERSARY_MODELS", "super").split(","))

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
            ("M1", "patch:cases/open_bugs/landley_toybox/572/one_line.diff"),
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


def attack_case(
    runner,
    client,
    case,
    out: Path,
    cands: list[tuple[str, dict[str, str], str]],
    ref_files=None,
    models: tuple[str, ...] = MODELS,
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
            text = adv.prompt(report, adv.how(case), poc, originals, files, diff)
            row: dict[str, Any] = {"case": case.id, "candidate": cid, "models": {}}
            inputs = []
            for model in models:
                # The project name for bring-your-own cases: their id is a config path, which on
                # Windows made the old cache name absolute and wrote it next to the config.
                slug = case.project if case.id.startswith("project:") else case.id
                cache = out / f"{slug}__{cid}__{model}.v{adv.PROMPT_VERSION}.inputs.json"
                if cache.exists():
                    got = json.loads(cache.read_text())
                    for g in got["inputs"]:
                        g["data"] = bytes.fromhex(g["data"])
                    usd = got["usd"]
                else:
                    spent0 = client.ledger.spent
                    used, notes = VARIANTS[model][0], []
                    try:
                        if model == "super_fb":
                            # D-0080: Super, then Ultra once when Super gives no usable input.
                            got_inputs, used, notes = adv.attack_with_fallback(
                                client, "super", text
                            )
                        else:
                            got_inputs, _ = adv.attack(
                                client, VARIANTS[model][0], text, VARIANTS[model][1]
                            )
                    except Exception as exc:  # noqa: BLE001 - e.g. no JSON: no inputs, not cached
                        print("model error", model, str(exc)[:200], flush=True)
                        row["models"][model] = {
                            "usd": client.ledger.spent - spent0,
                            "n_inputs": 0,
                            "error": str(exc)[:300],
                        }
                        continue
                    usd = client.ledger.spent - spent0
                    got = {"inputs": got_inputs, "usd": usd, "model_used": used, "notes": notes}
                    cache.write_text(
                        json.dumps(
                            {
                                "usd": usd,
                                "model_used": used,
                                "notes": notes,
                                "inputs": [i | {"data": i["data"].hex()} for i in got_inputs],
                            },
                            indent=1,
                        )
                    )
                for i in got["inputs"]:
                    inputs.append(i | {"name": f"{model}_{i['name']}", "model": model})
                row["models"][model] = {
                    "usd": usd,
                    "n_inputs": len(got["inputs"]),
                    "model_used": got.get("model_used", VARIANTS[model][0]),
                    "notes": got.get("notes", []),
                }
            if not inputs:
                row["error"] = "no inputs"
                results.append(row)
                continue
            base = adv.run_inputs(runner, case, baseline, inputs)
            try:
                pat = adv.run_inputs(runner, case, baseline, inputs, files)
            except RuntimeError as e:
                row["error"] = str(e)
                results.append(row)
                continue
            refr = adv.run_inputs(runner, case, ref, inputs) if ref else None
            for model in models:
                keep = {i["name"] for i in inputs if i["model"] == model}

                def sub(r: gc.Run | None, keep=keep) -> gc.Run | None:  # noqa: ANN001
                    if r is None:
                        return None
                    return gc.Run(
                        {k: v for k, v in r.rows.items() if k in keep},
                        {k: v for k, v in r.reports.items() if k in keep},
                    )

                verdict, detail, rows = adv.judge(
                    sub(base), sub(pat), sub(refr), target, case.finding.get("location") or ""
                )
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
                {m: row["models"][m].get("verdict") for m in models},
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
    out = root / "runs" / "adversary" / (which + os.environ.get("LEAKPROOF_ADVERSARY_TAG", ""))
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
                if src.startswith("patch:"):
                    from gate_manual import from_patch

                    path = root / src.removeprefix("patch:")
                    loaded.append((cid, from_patch(case, path), path.read_text(encoding="utf-8")))
                    continue
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
                summary += attack_case(runner, client, case, out, cands, models=ACTIVE)
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
                summary += attack_case(runner, client, c, out, cands, models=ACTIVE)
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
                    runner,
                    client,
                    c,
                    out,
                    [("winner", files, w["diff"])],
                    ref_files=dev["files"],
                    models=ACTIVE,
                )
        except Exception as exc:  # noqa: BLE001 - record and continue with the next case
            summary.append(
                {
                    "case": str(getattr(case, "id", case)),
                    "error": f"{type(exc).__name__}: {exc}"[:1500],
                }
            )
            print("error", getattr(case, "id", case), str(exc)[:300], flush=True)
        (out / "summary.json").write_text(json.dumps(summary, indent=1))
    (out / "summary.json").write_text(json.dumps(summary, indent=1))
    usd = sum(m.get("usd", 0) for s in summary for m in s.get("models", {}).values())
    print(f"done: {len(summary)} candidates, ${usd:.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
