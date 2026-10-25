#!/usr/bin/env python3
"""Allocation-failure check (D-0078, advisory): does a patch crash when an allocation fails where
the unpatched build does not?

scripts/alloc_fail.py --config X/leakproof.toml --out runs/<name> --from-record ID=REC:HYP:W ...

Each variant (unpatched, then every candidate) is rebuilt with malloc/calloc/realloc wrapped at
link time (`-Wl,--wrap=...` and a small shim; LD_PRELOAD cannot override ASan's allocator), the
reproducer is run once to count allocations K, then again with allocation N failing for
N = 1..min(K, 200). A finding is an N where the candidate dies with a sanitizer report or a
signal and the unpatched build does not die the same way. No model calls; needs Docker (workerq).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from leakproof import gate_fuzz as gf
from leakproof.cases.project import ProjectCase
from leakproof.gate import split
from leakproof.runner import LocalDockerRunner

LP = gf.LP
MAX_N = 200
SHIM = r"""
#include <stdio.h>
#include <stdlib.h>
void *__real_malloc(size_t); void *__real_calloc(size_t, size_t); void *__real_realloc(void *, size_t);
static long lp_n = -1, lp_count = 0;
static int lp_fail(void) {
  if (lp_n < 0) { const char *e = getenv("LP_FAIL_NTH"); lp_n = e ? atol(e) : 0; }
  return ++lp_count == lp_n;
}
__attribute__((destructor)) static void lp_report(void) {
  const char *f = getenv("LP_COUNT_FILE");
  if (f) { FILE *o = fopen(f, "w"); if (o) { fprintf(o, "%ld\n", lp_count); fclose(o); } }
}
void *__wrap_malloc(size_t n) { return lp_fail() ? NULL : __real_malloc(n); }
void *__wrap_calloc(size_t a, size_t b) { return lp_fail() ? NULL : __real_calloc(a, b); }
void *__wrap_realloc(void *p, size_t n) { return lp_fail() ? NULL : __real_realloc(p, n); }
"""
WRAP = f"-Wl,--wrap=malloc,--wrap=calloc,--wrap=realloc {LP}/failmalloc.o"


def script(case: ProjectCase, files: dict[str, str], k: int | None) -> str:
    build = case.gate_build_cmd(files) if files else case.cfg["build"]
    count = (
        f"LP_COUNT_FILE={LP}/count timeout 20 bash {LP}/repro.sh > /dev/null 2>&1 < /dev/null; "
        f"K=$(cat {LP}/count 2>/dev/null || echo 0)"
        if k is None
        else f"K={k}"
    )
    return f"""
clang -c -O0 -g {LP}/failmalloc.c -o {LP}/failmalloc.o || exit 96
export CFLAGS="$CFLAGS {WRAP}" CXXFLAGS="$CXXFLAGS {WRAP}" LDFLAGS="$LDFLAGS {WRAP}"
{{ {build} ; }} > {LP}/build.log 2>&1 || {{ tail -20 {LP}/build.log; exit 97; }}
{count}
printf '\\n@@LPGATE@@ k\\n%s' "$K"
# The first and the last {MAX_N // 2} allocations: a fuzz harness allocates for itself before the
# code under test runs, so the code's own allocations sit at the end.
NS=$( (seq 1 $K | head -{MAX_N // 2}; seq 1 $K | tail -{MAX_N // 2}) | sort -nu)
: > {LP}/rows
for N in $NS; do
  LP_FAIL_NTH=$N timeout 5 bash {LP}/repro.sh > /dev/null 2> {LP}/e < /dev/null; rc=$?
  echo "$N $rc $({gf.SIG} {LP}/e | tr ' ' '_')" >> {LP}/rows
done
printf '\\n@@LPGATE@@ rows\\n'; cat {LP}/rows
"""


def run(runner, case: ProjectCase, baseline, files: dict[str, str], k: int | None):  # noqa: ANN001
    res = runner.run(
        baseline,
        script(case, files, k),
        files={
            f"{LP}/failmalloc.c": SHIM.encode(),
            f"{LP}/repro.sh": (case.reproduce_cmd + "\n").encode(),
        }
        | {p: t.encode() for p, t in files.items()},
        env=case.build_env | case.reproduce_env,
        cwd=case.workdir,
        timeout_s=3600,
        network=False,
    )
    sec = split(res.stdout)
    rows = {}
    for line in sec.get("rows", "").splitlines():
        parts = line.split(" ")
        if len(parts) >= 2:
            rows[int(parts[0])] = (parts[1], parts[2] if len(parts) > 2 else "")
    k = int(sec.get("k", "0").strip() or 0)
    return k, rows, res.stdout[-800:] if res.exit_code in (96, 97) else ""


def dies(rc: str, sig: str) -> bool:
    # A sanitizer report, or a signal (128+n) other than timeout's 124.
    return bool(sig) or (rc.isdigit() and int(rc) > 128)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--from-record", action="append", default=[])
    args = ap.parse_args()
    case = ProjectCase.load(f"project:{args.config.resolve()}")
    runner = LocalDockerRunner(memory="4g", cpus=2)
    out: dict = {"case": case.project, "candidates": {}}
    try:
        baseline = case.prepare(runner)
        cands = {}
        for spec in args.from_record:
            cid, ref = spec.split("=", 1)
            rec_path, hyp, idx = ref.rsplit(":", 2)
            rec = json.loads(Path(rec_path).read_text())
            w = next(
                w
                for w in rec["workers"]
                if (w["hypothesis_id"], w["worker_index"]) == (hyp, int(idx))
            )
            cands[cid] = w["files"]
        # K from the first candidate (the unpatched reproducer crashes before its count is written).
        first = next(iter(cands.values()))
        k, _, err = run(runner, case, baseline, first, None)
        out["k"] = k
        _, base_rows, err0 = run(runner, case, baseline, {}, k)
        out["baseline_error"] = err0
        for cid, files in cands.items():
            _, rows, errc = run(runner, case, baseline, files, k)
            findings = [
                {"n": n, "patched": rows[n], "unpatched": base_rows.get(n)}
                for n in sorted(rows)
                if dies(*rows[n]) and (base_rows.get(n) is None or rows[n][1] != base_rows[n][1])
            ]
            out["candidates"][cid] = {
                "findings": findings[:10],
                "n_findings": len(findings),
                "error": errc,
            }
            print(cid, "k", k, "findings", len(findings), findings[:2], errc[:200], flush=True)
    finally:
        case.cleanup(runner)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "alloc_fail.json").write_text(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
