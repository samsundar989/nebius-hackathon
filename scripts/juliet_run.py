#!/usr/bin/env python3
"""Build + run the Juliet smoke set through the Runner and record each case (kickoff 3.5).

Per case, in one container (network off): build bad-only (-DOMITGOOD) and good-only (-DOMITBAD)
with ASan+UBSan, run both, parse the reports. Bad must produce the expected finding; good must
be sanitizer-clean (that is the gate's "fixed" oracle).

Writes cases/juliet/<id>.json, the raw bad-run report to tests/fixtures/juliet/<id>.log, and the
per-CWE table to runs/juliet_summary.json (rendered into docs/REPORT_E0.md by hand).
Usage: uv run python scripts/juliet_run.py [--only ID] [--jobs 3] [--runner docker]
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import os
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

from leakproof.findings import parse_report, primary
from leakproof.runner import ImageRef, get_runner

ROOT = Path(__file__).resolve().parent.parent
JULIET = Path.home() / ".cache" / "leakproof" / "juliet" / "C"
IMAGE = ImageRef("docker", "leakproof/cpp-sanitizers:e0")
# Same toolchain on Sandboxes (scripts/sandboxes_setup.py); D-0053.
IMAGES = {"docker": IMAGE, "sandboxes": ImageRef("sandboxes", "tag:lp-cpp-sanitizers")}
# -O0, not the kickoff's -O1: at -O1 clang deletes malloc/free/free sequences, hiding double
# frees (2/15 CWE-415 cases), and -O1 -fno-omit-frame-pointer makes LSan miss leaks. Measured;
# see docs/REPORT_E0.md and D-0021.
CFLAGS = "-fsanitize=address,undefined -g -O0 -DINCLUDEMAIN"
RUN_ENV = {
    "ASAN_OPTIONS": "detect_leaks=1:abort_on_error=0:symbolize=1",
    # Stale pointer copies on the stack hide small leaks from LSan's conservative scan.
    "LSAN_OPTIONS": os.environ.get("LP_LSAN_OPTIONS", "use_stacks=0"),
    "UBSAN_OPTIONS": "print_stacktrace=1:halt_on_error=0",
}
SUPPORT = ["io.c", "std_testcase.h", "std_testcase_io.h", "std_thread.h"]
MARK = "@@LEAKPROOF@@"
# Root causes established by hand (docs/REPORT_E0.md); a miss without an entry is a harness bug.
NOT_REPRODUCIBLE = {
    "CWE401_Memory_Leak__char_calloc_68": "leaked block is still referenced from a global at exit, so LSan treats it as reachable (by design; use_globals=0 would report it but also flags libc/iostream globals)",
    "CWE401_Memory_Leak__new_struct_twoIntsStruct_68": "leaked block is still referenced from a global at exit, so LSan treats it as reachable (by design; use_globals=0 would report it but also flags libc/iostream globals)",
    "CWE401_Memory_Leak__new_TwoIntsClass_45": "leaked block is still referenced from a global at exit, so LSan treats it as reachable (by design; use_globals=0 would report it but also flags libc/iostream globals)",
    "CWE401_Memory_Leak__strdup_wchar_t_45": "leaked block is still referenced from a global at exit, so LSan treats it as reachable (by design; use_globals=0 would report it but also flags libc/iostream globals)",
    "CWE401_Memory_Leak__destructor_01": "class-based Juliet case: _bad.cpp and _good1.cpp each define main(); our build links every file of the case into one program (multiple definition of main) - a harness limitation, not the sanitizer",
    "CWE401_Memory_Leak__virtual_destructor_01": "class-based Juliet case: _bad.cpp and _good1.cpp each define main(); our build links every file of the case into one program (multiple definition of main) - a harness limitation, not the sanitizer",
    "CWE401_Memory_Leak__twoIntsStruct_calloc_68": "leaked block is still referenced from a "
    "global at exit, so LSan treats it as reachable (by design; use_globals=0 would report it "
    "but also flags libc/iostream globals)",
    "CWE416_Use_After_Free__malloc_free_wchar_t_62": "the freed buffer is only read inside "
    "wprintf in uninstrumented libc, which ASan does not intercept",
}


def build_commands(case: dict, variant: str, extra: str = "") -> tuple[str, str]:
    """(build_cmd, run_cmd) for variant 'bad' or 'good', relative to /work."""
    cflags = f"{CFLAGS} {extra}".strip()
    omit = "-DOMITGOOD" if variant == "bad" else "-DOMITBAD"
    srcs = [f"case/{f}" for f in case["files"] if f.endswith((".c", ".cpp"))]
    out = f"bin/{variant}"
    inc = "-Isupport -Icase"
    if case["lang"] == "c++":
        cxx = [s for s in srcs if s.endswith(".cpp")]
        cc = [s for s in srcs if s.endswith(".c")]
        objs = " ".join(f"bin/{Path(s).stem}_{variant}.o" for s in cc)
        build = f"clang {cflags} {omit} {inc} -c support/io.c -o bin/io_{variant}.o"
        for s in cc:
            build += f" && clang {cflags} {omit} {inc} -c {s} -o bin/{Path(s).stem}_{variant}.o"
        build += (
            f" && clang++ {cflags} {omit} {inc} {' '.join(cxx)} bin/io_{variant}.o {objs} -o {out}"
        )
    else:
        build = f"clang {cflags} {omit} {inc} support/io.c {' '.join(srcs)} -o {out}"
    run = f"timeout 30 ./{out} < /dev/null"
    return build, run


def case_script(case: dict, extra: str = "") -> str:
    lines = ["mkdir -p bin out"]
    for v in ("bad", "good"):
        build, run = build_commands(case, v, extra)
        lines += [
            f"( {build} ) > out/build_{v}.log 2>&1; echo $? > out/build_{v}.rc",
            f"if [ $(cat out/build_{v}.rc) = 0 ]; then ( {run} ) > out/stdout_{v}.log "
            f"2> out/stderr_{v}.log; echo $? > out/run_{v}.rc; else echo -1 > out/run_{v}.rc; "
            f"touch out/stdout_{v}.log out/stderr_{v}.log; fi",
        ]
    for name in ("build_bad", "build_good", "stderr_bad", "stderr_good", "stdout_bad"):
        lines.append(f"echo '{MARK} {name}'; cat out/{name}.log")
    for name in ("build_bad", "run_bad", "build_good", "run_good"):
        lines.append(f"echo '{MARK} {name}.rc'; cat out/{name}.rc")
    return "\n".join(lines)


def split_sections(stdout: str) -> dict[str, str]:
    parts = re.split(rf"^{re.escape(MARK)} (\S+)\n", stdout, flags=re.M)
    return {parts[i]: parts[i + 1] for i in range(1, len(parts) - 1, 2)}


def run_case(runner, case: dict, extra: str = "") -> dict:  # noqa: ANN001 - any Runner
    case_dir = JULIET / case["dir"]
    files: dict[str, bytes | Path] = {f"case/{f}": case_dir / f for f in case["files"]}
    files.update({f"support/{f}": JULIET / "testcasesupport" / f for f in SUPPORT})
    t0 = time.monotonic()
    res = runner.run(
        IMAGES[getattr(runner, "name", "docker")],
        case_script(case, extra),
        files=files,
        env=RUN_ENV,
        cwd="/work",
        timeout_s=300,
        network=False,
    )
    wall = time.monotonic() - t0
    sec = split_sections(res.stdout)
    rc = {k[:-3]: int(v.strip() or -99) for k, v in sec.items() if k.endswith(".rc")}
    bad_report, good_report = sec.get("stderr_bad", ""), sec.get("stderr_good", "")
    bad_findings, good_findings = parse_report(bad_report), parse_report(good_report)
    p = primary(bad_findings)
    build_bad, run_bad = build_commands(case, "bad", extra)
    build_good, run_good = build_commands(case, "good", extra)
    detected = rc.get("run_bad", 0) != 0 and bool(bad_report.strip())
    return {
        **case,
        "source_root": "juliet-1.3/C",
        "support_files": [f"testcasesupport/{f}" for f in SUPPORT],
        "image": IMAGE.ref,
        "env": RUN_ENV,
        "build_cmd_bad": build_bad,
        "run_cmd_bad": run_bad,
        "build_cmd_good": build_good,
        "run_cmd_good": run_good,
        "build_bad_ok": rc.get("build_bad") == 0,
        "build_good_ok": rc.get("build_good") == 0,
        "bad_exit": rc.get("run_bad"),
        "good_exit": rc.get("run_good"),
        "detected": detected,
        "parsed": p is not None,
        "parsed_kind_matches": p is not None and p.kind == case["expected_kind"],
        "reproducible": detected and p is not None and p.kind == case["expected_kind"],
        "not_reproducible_reason": None if detected else NOT_REPRODUCIBLE.get(case["id"]),
        "finding": p.to_dict(include_raw=False) if p else None,
        "all_bad_kinds": [f.kind for f in bad_findings],
        "good_clean": rc.get("run_good") == 0 and not good_findings,
        # Juliet good() paths may leak incidentally (CWE-415/416 say so in comments); the oracle
        # for those CWEs is "no memory-safety error", with leaks reported separately.
        "good_clean_target": not [
            f for f in good_findings if case["expected_kind"] == "leak" or f.kind != "leak"
        ],
        "good_findings": [f.kind for f in good_findings],
        "build_log_bad_tail": sec.get("build_bad", "")[-1500:] if rc.get("build_bad") else "",
        "wall_s": round(wall, 2),
        "container_peak_kb": res.max_rss_kb,
        "_bad_report": bad_report,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only")
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--runner", default="docker")
    ap.add_argument("--selection", type=Path, default=ROOT / "cases" / "juliet" / "selection.json")
    ap.add_argument("--summary-suffix", default="", help="runs/juliet_summary<suffix>.json")
    ap.add_argument(
        "--extra-cflags", default="", help="sensitivity runs; results not written to cases/"
    )
    args = ap.parse_args()
    selection = json.loads(args.selection.read_text())["cases"]
    if args.only:
        selection = [c for c in selection if c["id"] == args.only]
    runner = (
        get_runner(args.runner, memory="1536m", cpus=1.0)
        if args.runner == "docker"
        else (get_runner(args.runner))
    )
    fx_dir = ROOT / "tests" / "fixtures" / "juliet"
    fx_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.monotonic()
    results = []
    with cf.ThreadPoolExecutor(args.jobs) as pool:
        for r in pool.map(lambda c: run_case(runner, c, args.extra_cflags), selection):
            report = r.pop("_bad_report")
            if args.extra_cflags:
                r["extra_cflags"] = args.extra_cflags
                results.append(r)
                print(f"{r['id']}: detected={r['detected']} kinds={r['all_bad_kinds']}", flush=True)
                continue
            (fx_dir / f"{r['id']}.log").write_text(report)
            (ROOT / "cases" / "juliet" / f"{r['id']}.json").write_text(
                json.dumps(r, indent=1) + "\n"
            )
            ok = r["reproducible"] and r["good_clean_target"]
            flag = "OK " if ok else "BAD"
            print(
                f"{flag} {r['id']}: bad_exit={r['bad_exit']} kinds={r['all_bad_kinds']} "
                f"good_clean_target={r['good_clean_target']} {r['wall_s']}s",
                flush=True,
            )
            results.append(r)
    table: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for r in results:
        row = table[r["cwe"]]
        row["cases"] += 1
        row["built"] += r["build_bad_ok"] and r["build_good_ok"]
        row["detected"] += r["detected"]
        row["parsed"] += r["parsed"]
        row["kind_match"] += r["parsed_kind_matches"]
        row["good_clean"] += r["good_clean"]
        row["good_clean_target"] += r["good_clean_target"]
    summary = {
        "wall_s": round(time.monotonic() - t0, 1),
        "jobs": args.jobs,
        "per_cwe": {k: dict(v) for k, v in sorted(table.items())},
        "mean_case_wall_s": round(sum(r["wall_s"] for r in results) / max(len(results), 1), 2),
    }
    suffix = "_extra" if args.extra_cflags else args.summary_suffix
    summary["cflags"] = f"{CFLAGS} {args.extra_cflags}".strip()
    (ROOT / "runs" / f"juliet_summary{suffix}.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
