#!/usr/bin/env python3
"""Cross-candidate differential (D-0070): do a case's verified candidates behave the same?

Each verified candidate already matches the baseline on every corpus input the baseline runs
cleanly, so they can only disagree where the baseline crashed (PoC, amplified variants) or on
inputs nobody tried. Per case with 2+ distinct verified diffs: build every candidate on one
baseline, fuzz each 30 s for new inputs, then run the union (corpus + PoC + amplified + fuzz
finds) through every build and compare exit code, stdout hash and sanitizer signature.

Output runs/cross_diff/<case>.json: behaviour groups (candidates with identical rows) and up to
8 inputs that separate them. One group = agree; more = `ambiguous`. No model calls, $0.

Needs Docker: submit through workerq (scripts/lp_job.ps1), resumable per case.
"""

from __future__ import annotations

import argparse
import base64
import contextlib
import io
import json
import os
import sys
import tarfile
import time
from pathlib import Path

from leakproof import gate_fuzz as gf
from leakproof.cases import load_case
from leakproof.config import RUNS_DIR
from leakproof.gate import ArvoGate, split
from leakproof.runner import LocalDockerRunner
from leakproof.semantic import verified_candidates

OUT = RUNS_DIR / "cross_diff"
FUZZ_SECONDS = 30
FUZZ_KEEP = 150


def progress(frac: float) -> None:
    path = os.environ.get("WORKERQ_PROGRESS")
    if path:
        with contextlib.suppress(OSError):
            Path(path).write_text(f"{frac:.3f}")


def untar(blob: bytes, top: str) -> dict[str, bytes]:
    out = {}
    if not blob:
        return out
    with tarfile.open(fileobj=io.BytesIO(blob)) as t:
        for m in t.getmembers():
            if m.isfile() and m.name.startswith(f"{top}/"):
                out[m.name.split("/", 1)[1]] = t.extractfile(m).read()
    return out


def build_and_fuzz(gate: ArvoGate, case, files: dict[str, str], seeds: dict[str, bytes], seed: int):  # noqa: ANN001
    """Build one candidate (image saved), fuzz it; returns (image or None, new inputs)."""
    h = gate.harness
    script = f"""
{{ {case.gate_build_cmd(files)} ; }} > /tmp/compile.log 2>&1 || {{ tail -c 3000 /tmp/compile.log; exit 97; }}
mkdir -p {gf.LP}/fz {gf.LP}/art
ASAN_OPTIONS={gf.ASAN_DIFF} timeout {FUZZ_SECONDS + 120} {h} -max_total_time={FUZZ_SECONDS} \\
  -max_len={max(8 * len(gate.poc), 4096)} -seed={seed} {gf.FUZZ_FLAGS} -artifact_prefix={gf.LP}/art/ \\
  {gf.LP}/fz {gf.LP}/seeds > /dev/null 2>&1
cd {gf.LP} && ls -S fz | tail -{FUZZ_KEEP} | sed 's|^|fz/|' > keep && tar czf fz.tgz -T keep
printf '\\n@@LPGATE@@ fz_b64\\n'; base64 -w0 {gf.LP}/fz.tgz
"""
    res = gate.runner.run(
        gate.baseline,
        script,
        files={k: v.encode() for k, v in files.items()}
        | {f"{gf.LP}/seeds/{n}": d for n, d in seeds.items()},
        env=case.build_env | (getattr(case, "reproduce_env", None) or {}),
        cwd=case.workdir,
        timeout_s=3600,
        network=False,
        save=True,
    )
    if res.exit_code == 97 or res.image is None:
        return None, {}, res.stdout[-1500:]
    blob = base64.b64decode(split(res.stdout).get("fz_b64", "").strip() or b"")
    return res.image, untar(blob, "fz"), ""


def rows(gate: ArvoGate, image, inputs: dict[str, bytes]) -> dict[str, list[str]]:  # noqa: ANN001
    res = gate.runner.run(
        image,
        gf.corpus_run_script(gate.harness, gf.ASAN_DIFF, "x"),  # `files` fill {LP}/corpus
        files={f"{gf.LP}/corpus/{n}": d for n, d in inputs.items()},
        cwd=gate.case.workdir,
        timeout_s=3600,
        network=False,
    )
    return {
        n: [r.rc, r.out, r.sig] for n, r in gf.parse_rows(split(res.stdout).get("x", "")).items()
    }


def cross_case(case_id: str, cands: dict, runner: LocalDockerRunner) -> dict:
    t0 = time.monotonic()
    case = load_case(case_id)
    rec: dict = {"case": case_id, "candidates": []}
    images = []
    try:
        baseline = case.prepare(runner)
        gate = ArvoGate(case, runner, baseline)
        un = gate.unpatched()
        rec["unpatched"] = un.detail
        if un.status != "pass" or gate.harness is None:
            rec["error"] = f"baseline: {un.detail}"
            return rec
        corpus = untar(gate.corpus_tgz, "corpus")
        clean = {
            n: d
            for n, d in corpus.items()
            if (r := gate.base_diff.get(n)) and not r.sig and r.rc == "0"
        }
        seeds = clean | {"poc": gate.poc} | {f"amp_{n}": d for n, d in gate.amp}
        inputs = corpus | {"poc": gate.poc} | {f"amp_{n}": d for n, d in gate.amp}
        for i, (key, cand) in enumerate(cands.items()):
            image, found, err = build_and_fuzz(gate, case, cand["files"], seeds, seed=11 + i)
            rec["candidates"].append(
                {
                    "change": key,
                    "members": cand["members"],
                    "built": image is not None,
                    "error": err,
                    "fuzz_inputs": len(found),
                }
            )
            images.append(image)
            inputs |= {f"fz{i}_{n}": d for n, d in found.items()}
        table = {}
        for i, image in enumerate(images):
            if image is not None:
                table[i] = rows(gate, image, inputs)
        rec["inputs"] = len(inputs)
        groups: dict[str, list[int]] = {}
        for i, r in table.items():
            groups.setdefault(json.dumps(sorted(r.items())), []).append(i)
        rec["groups"] = list(groups.values())
        rec["verdict"] = "agree" if len(groups) <= 1 else "ambiguous"
        if len(groups) > 1:
            first = [g[0] for g in groups.values()]
            sep = [
                n for n in sorted(inputs) if len({json.dumps(table[i].get(n)) for i in first}) > 1
            ]
            rec["separating_inputs"] = [
                {
                    "input": n,
                    "bytes": len(inputs[n]),
                    "b64": gf.b64(inputs[n]) if len(inputs[n]) <= 2048 else None,
                    "rows": {str(i): table[i].get(n) for i in first},
                }
                for n in sep[:8]
            ]
            rec["separating_count"] = len(sep)
    except Exception as exc:  # noqa: BLE001 - record and continue with the next case
        rec["error"] = f"{type(exc).__name__}: {exc}"[:2000]
    finally:
        for image in images:
            if image is not None:
                with contextlib.suppress(Exception):
                    runner.remove_image(image)
        if hasattr(case, "cleanup"):
            case.cleanup(runner)
        rec["elapsed_s"] = round(time.monotonic() - t0, 1)
    return rec


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--cases", help="comma-separated case ids (default: every multi-candidate case)"
    )
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    runner = LocalDockerRunner(memory="4g", cpus=2)
    allc = verified_candidates()
    todo = [c for c, v in sorted(allc.items()) if len(v["candidates"]) > 1]
    if args.cases:
        todo = [c for c in args.cases.split(",") if c]
    for i, cid in enumerate(todo):
        out = OUT / f"{cid}.json"
        if out.exists() and "error" not in json.loads(out.read_text()):
            continue
        rec = cross_case(cid, allc[cid]["candidates"], runner)
        out.write_text(json.dumps(rec, indent=1))
        print(cid, rec.get("verdict"), rec.get("groups"), rec.get("error", "")[:200], flush=True)
        progress((i + 1) / len(todo))
    return 0


if __name__ == "__main__":
    sys.exit(main())
