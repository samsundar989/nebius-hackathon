#!/usr/bin/env python3
"""CUDA cases end to end on a Kaggle T4 (strategist order D; D-0063): find, fix, re-verify.

  scripts/cuda_fix.py baseline   one kernel run: each case under its compute-sanitizer tool
  scripts/cuda_fix.py fix        locally: Ultra plans, 4 Lightning workers edit (no GPU build)
  scripts/cuda_fix.py verify     one kernel run: originals + every candidate, then verdicts
  scripts/cuda_fix.py all        the three in order (two kernel runs, a few T4 minutes)

Verdict per candidate (gate side; the manifest cases/cuda/cases.json is never shown to workers):
unpatched_trips (the original reports the defect) -> diff_scope -> build -> sanitizer (parsed
report empty, ERROR SUMMARY 0, no tool error; D-0028: never the exit code) -> behavior (stdout
has every expected line). Output: runs/p5_cuda/{baseline,candidates,verify,verdicts}.json.
"""

from __future__ import annotations

import argparse
import base64
import concurrent.futures as cf
import json
import re
import sys
import tempfile
import time
from pathlib import Path

from kaggle_cuda import kaggle

from leakproof.cases.base import Window
from leakproof.config import RUNS_DIR, load_dotenv
from leakproof.findings import primary
from leakproof.findings.compute_sanitizer import parse_compute_sanitizer
from leakproof.gate import Check, diff_scope
from leakproof.llm import CostLedger, LLMClient
from leakproof.planner import plan
from leakproof.worker import run_worker

ROOT = Path(__file__).resolve().parent.parent
CASES = ROOT / "cases" / "cuda"
OUT = RUNS_DIR / "p5_cuda"
SLUG = "leakproof-cuda-gate"
KERNEL = """\
import json, os, subprocess, pathlib, base64
jobs = json.loads(base64.b64decode({payload!r}).decode())
w = pathlib.Path("/kaggle/working"); res = {{}}
env = dict(os.environ); env["PATH"] = "/usr/local/cuda/bin:" + env.get("PATH", "")
def run(cmd, t=300):
    try:
        p = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=t)
        return p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired:
        return 124, "", "timeout"
for jid, j in jobs.items():
    d = w / jid; d.mkdir(parents=True, exist_ok=True)
    (d / "case.cu").write_text(j["source"])
    rc, o, e = run(["nvcc", "-g", "-lineinfo", "-Wno-deprecated-gpu-targets", "-o", str(d / "bin"), str(d / "case.cu")])
    r = {{"build_rc": rc, "build_log": (o + e)[-3000:]}}
    if rc == 0:
        rc, o, e = run([str(d / "bin")], 120)
        r.update(run_rc=rc, stdout=o[-4000:])
        rc, o, e = run(["compute-sanitizer"] + j["tool"].split() + ["--print-limit", "10", str(d / "bin")])
        r.update(san_rc=rc, san_log=(o + e)[-12000:])
    res[jid] = r
(w / "results.json").write_text(json.dumps(res, indent=1))
print(json.dumps({{k: {{"build": v["build_rc"], "san": v.get("san_rc")}} for k, v in res.items()}}))
"""


def manifest() -> dict:
    return json.loads((CASES / "cases.json").read_text())["cases"]


def kaggle_run(jobs: dict, user: str, timeout_min: int = 25) -> dict:
    payload = base64.b64encode(json.dumps(jobs).encode()).decode()
    with tempfile.TemporaryDirectory() as tmp:
        kdir = Path(tmp)
        (kdir / "run.py").write_text(KERNEL.format(payload=payload))
        meta = {
            "id": f"{user}/{SLUG}",
            "title": SLUG,
            "code_file": "run.py",
            "language": "python",
            "kernel_type": "script",
            "is_private": True,
            "enable_gpu": True,
            "enable_internet": False,
            "dataset_sources": [],
            "competition_sources": [],
            "kernel_sources": [],
        }
        (kdir / "kernel-metadata.json").write_text(json.dumps(meta))
        t0 = time.time()
        push = kaggle("kernels", "push", "-p", str(kdir))
        if push.returncode != 0:
            raise RuntimeError(f"kaggle push failed: {push.stdout[-400:]} {push.stderr[-400:]}")
    deadline, status = time.time() + timeout_min * 60, ""
    while time.time() < deadline:
        time.sleep(20)
        status = kaggle("kernels", "status", f"{user}/{SLUG}").stdout.strip().lower()
        if any(s in status for s in ("complete", "error", "cancel")):
            break
    out = Path(tempfile.mkdtemp())
    kaggle("kernels", "output", f"{user}/{SLUG}", "-p", str(out), "-o")
    res = out / "results.json"
    if not res.exists():
        raise RuntimeError(f"kernel finished with '{status}' and no results.json")
    data = json.loads(res.read_text())
    data["_meta"] = {"status": status, "wall_s": round(time.time() - t0, 1)}
    return data


def sanitizer_check(r: dict) -> Check:
    log = r.get("san_log", "")
    if r.get("build_rc") != 0:
        return Check("skipped", "not built")
    if "COMPUTE-SANITIZER" not in log or re.search(r"=+ (Internal )?Error: (?!Race)", log):
        return Check("inconclusive", "compute-sanitizer did not run cleanly (tool error)")
    findings = parse_compute_sanitizer(log)
    m = re.search(r"ERROR SUMMARY: (\d+) error", log)
    if findings or (m and int(m.group(1)) > 0):
        p = primary(findings)
        return Check(
            "fail", f"{p.kind if p else 'error'}: {(p.summary if p else log[-200:])[:200]}"
        )
    return Check("pass", "no compute-sanitizer report, ERROR SUMMARY 0")


def step_baseline(user: str) -> dict:
    m = manifest()
    jobs = {
        f"{c}__orig": {"source": (CASES / f"{c}.cu").read_text(), "tool": v["tool"]}
        for c, v in m.items()
    }
    res = kaggle_run(jobs, user)
    base = {"_meta": res.pop("_meta")}
    for c in m:
        r = res[f"{c}__orig"]
        p = primary(parse_compute_sanitizer(r.get("san_log", "")))
        base[c] = r | {"finding": p.to_dict(include_raw=False) if p else None}
    (OUT / "baseline.json").write_text(json.dumps(base, indent=1))
    print({c: (base[c]["finding"] or {}).get("kind") for c in m}, base["_meta"])
    return base


def step_fix(workers: int, budget: float) -> dict:
    load_dotenv()
    base = json.loads((OUT / "baseline.json").read_text())
    cands: dict = {}
    for c in manifest():
        finding = base[c].get("finding")
        if not finding:
            print(f"{c}: baseline did not trip; skipped")
            continue
        path = f"{c}.cu"
        text = (CASES / path).read_text()
        client = LLMClient(ledger=CostLedger(budget=budget), run_id=f"p5_cuda:{c}")
        win = [Window(path, 1, len(text.splitlines()), text)]
        desc = (
            "A single CUDA C++ program built with `nvcc -g -lineinfo` and checked with NVIDIA "
            "compute-sanitizer on a T4 GPU. It prints a checksum of its result."
        )
        pl = plan(client, finding, win, [path], desc, model="ultra")
        hyps = [pl.hypotheses[i % len(pl.hypotheses)] for i in range(workers)]

        kw = {
            "finding": finding,
            "root_cause": pl.root_cause,
            "sources": {path: text},
            "windows": win,
            "restore": lambda _p, t: t,
            "build": None,
            "max_completion_tokens": 6_000,
        }
        with cf.ThreadPoolExecutor(workers) as pool:
            futs = [
                pool.submit(run_worker, client, index=i, hypothesis=h, **kw)
                for i, h in enumerate(hyps)
            ]
            done = [f.result().to_dict() for f in futs]
        cands[c] = {
            "plan": pl.to_dict(),
            "workers": done,
            "usd": round(client.ledger.spent, 6),
        }
        print(f"{c}: {[w['status'] for w in done]} ${client.ledger.spent:.4f}")
    (OUT / "candidates.json").write_text(json.dumps(cands, indent=1))
    return cands


def step_verify(user: str) -> dict:
    m = manifest()
    base = json.loads((OUT / "baseline.json").read_text())
    cands = json.loads((OUT / "candidates.json").read_text())
    jobs, scope = {}, {}
    for c, v in m.items():
        jobs[f"{c}__orig"] = {"source": (CASES / f"{c}.cu").read_text(), "tool": v["tool"]}
        seen: set[str] = set()
        for w in cands.get(c, {}).get("workers", []):
            if w["status"] != "edited" or w["diff"] in seen:
                continue
            seen.add(w["diff"])
            jid = f"{c}__{w['hypothesis_id']}w{w['worker_index']}"
            path = f"{c}.cu"
            scope[jid] = diff_scope(w["diff"], [path], {path}, None, "other", "")
            if scope[jid].status == "pass":
                jobs[jid] = {"source": w["files"][path], "tool": v["tool"]}
    res = kaggle_run(jobs, user)
    (OUT / "verify.json").write_text(json.dumps(res, indent=1))
    verdicts: dict = {"_meta": res.get("_meta")}
    for c, v in m.items():
        orig = sanitizer_check(res.get(f"{c}__orig", {}))
        trips = Check("pass" if orig.status == "fail" else "fail", f"original: {orig.detail}")
        rows = []
        for jid in [j for j in scope if j.startswith(f"{c}__")]:
            r = res.get(jid, {})
            checks = {"unpatched_trips": trips, "diff_scope": scope[jid]}
            if scope[jid].status == "pass":
                checks["build"] = Check(
                    "pass" if r.get("build_rc") == 0 else "fail", r.get("build_log", "")[-300:]
                )
                checks["sanitizer"] = sanitizer_check(r)
                out = r.get("stdout", "")
                missing = [e for e in v["expect"] if e not in out]
                checks["behavior"] = Check(
                    "fail" if missing else "pass",
                    f"missing {missing}" if missing else "expected output",
                )
            order = ["unpatched_trips", "diff_scope", "build", "sanitizer", "behavior"]
            verdict = "verified"
            for name in order:
                st = checks.get(name, Check("skipped")).status
                if st in ("fail", "inconclusive"):
                    verdict = {
                        "unpatched_trips": "inconclusive:unpatched_does_not_trip",
                        "diff_scope": "rejected:diff_scope",
                        "build": "build_failed",
                        "sanitizer": f"rejected:{checks[name].detail.split(':')[0]}"
                        if st == "fail"
                        else "inconclusive:sanitizer",
                        "behavior": "silenced_only",
                    }[name]
                    break
            rows.append(
                {
                    "id": jid,
                    "verdict": verdict,
                    "checks": {k: x.to_dict() for k, x in checks.items()},
                }
            )
        best = next((r for r in rows if r["verdict"] == "verified"), rows[0] if rows else None)
        verdicts[c] = {
            "baseline_kind": (base[c].get("finding") or {}).get("kind"),
            "verdict": best["verdict"] if best else "no_candidate",
            "candidates": rows,
            "usd": cands.get(c, {}).get("usd", 0.0),
        }
        print(f"{c}: {verdicts[c]['verdict']}  {[r['verdict'] for r in rows]}")
    (OUT / "verdicts.json").write_text(json.dumps(verdicts, indent=1))
    return verdicts


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=["baseline", "fix", "verify", "all"])
    ap.add_argument("--user", default="neopok919")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--budget", type=float, default=0.3)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    if args.step in ("baseline", "all"):
        step_baseline(args.user)
    if args.step in ("fix", "all"):
        step_fix(args.workers, args.budget)
    if args.step in ("verify", "all"):
        step_verify(args.user)
    return 0


if __name__ == "__main__":
    sys.exit(main())
