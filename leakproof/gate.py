"""The evidence gate (v0). Runs as its own process; workers never import this module.

    python -m leakproof.gate --case ID --baseline IMAGE [--workdir DIR] --candidates C.json --out V.json

Every check starts from the baseline checkpoint in a fresh container with the network off:
  1 unpatched_trips  the unpatched build still trips under the same flags (D-0020)
  2 patched          patched build + PoC: no sanitizer report (tool error = inconclusive, D-0028)
  3 tests            project tests pass under ASan (Juliet: good-only build stays clean)
  3b behavior        Juliet: program output unchanged (leaks) / not truncated (crashes)
  4 diff_scope       only editable source files; no sanitizer, flag or exit tricks; no removed
                     free() without a replacement unless the defect is a double free
Verdict: verified | silenced_only | rejected:<reason> | build_failed | inconclusive:<reason>
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from leakproof.cases.arvo import BUILD_ENV, ArvoCase
from leakproof.cases.juliet import JulietCase
from leakproof.findings import parse_report, primary
from leakproof.runner import ImageRef, LocalDockerRunner

MARK = "@@LPGATE@@"
SOURCE_EXT = (".c", ".h", ".cc", ".cpp", ".cxx", ".hpp", ".hh", ".inc")
FORBIDDEN_DIRS = re.compile(r"/(tests?|testsuite|fuzz|fuzzing|oss-fuzz|regress)/", re.I)
FORBIDDEN_ADDED = [
    (
        re.compile(
            r"no_sanitize|__asan_|__lsan_|__msan_|__sanitizer_|__has_feature\s*\(\s*address_sanitizer"
        ),
        "sanitizer_annotation",
    ),
    (
        re.compile(r"[AL]SAN_OPTIONS|UBSAN_OPTIONS|__lsan_default|__asan_default"),
        "sanitizer_options",
    ),
    (re.compile(r"\b(_exit|_Exit|exit|abort|quick_exit)\s*\("), "exit_bypass"),
    (re.compile(r"#\s*define\s+(malloc|free|calloc|realloc|strdup)\b"), "allocator_redefine"),
    (re.compile(r"#\s*pragma\b"), "pragma"),
    (re.compile(r"FUZZING_BUILD_MODE|LLVMFuzzerTestOneInput"), "fuzz_harness"),
]
# `if (p == NULL) {exit(-1);}` after an allocation is the one exit an edit may add.
ALLOC_FAILURE_GUARD = re.compile(r"if\s*\(\s*(\w+\s*==\s*NULL|NULL\s*==\s*\w+|!\s*\w+)\s*\)")
FREE_CALL = re.compile(r"\b(free|g_free|xfree|[A-Za-z_]\w*_free)\s*\(|\bdelete\b")


@dataclass
class Check:
    status: str  # pass | fail | skipped | inconclusive
    detail: str = ""

    def to_dict(self) -> dict[str, str]:
        return {"status": self.status, "detail": self.detail}


@dataclass
class GateResult:
    hypothesis_id: str
    worker_index: int
    verdict: str
    checks: dict[str, Check] = field(default_factory=dict)
    patched_report_tail: str = ""
    elapsed_s: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        d = self.__dict__.copy()
        d["checks"] = {k: v.to_dict() for k, v in self.checks.items()}
        return d


# ------------------------------------------------------------------------------- pure logic
def diff_scope(
    diff: str,
    paths: list[str],
    allowed: set[str] | None,
    src_root: str | None,
    strategy: str,
    kind: str,
) -> Check:
    for p in paths:
        if allowed is not None and p not in allowed:
            return Check("fail", f"edited {p}, not an editable source file")
        if src_root is not None and (
            not p.startswith(src_root)
            or not p.endswith(SOURCE_EXT)
            or FORBIDDEN_DIRS.search(p[len(src_root) - 1 :])
        ):
            return Check(
                "fail", f"edited {p}: outside project sources or in tests/fuzz/build files"
            )
    added = [ln[1:] for ln in diff.splitlines() if ln.startswith("+") and not ln.startswith("+++")]
    removed = [
        ln[1:] for ln in diff.splitlines() if ln.startswith("-") and not ln.startswith("---")
    ]
    for pattern, reason in FORBIDDEN_ADDED:
        hit = next(
            (
                ln
                for ln in added
                if pattern.search(ln)
                and not (reason == "exit_bypass" and ALLOC_FAILURE_GUARD.search(ln))
            ),
            None,
        )
        if hit is not None:
            return Check("fail", f"{reason}: {hit.strip()[:120]}")
    frees_removed = sum(len(FREE_CALL.findall(ln)) for ln in removed)
    frees_added = sum(len(FREE_CALL.findall(ln)) for ln in added)
    if frees_removed > frees_added and strategy != "remove_free" and kind != "double-free":
        return Check(
            "fail", f"removed_free: {frees_removed} free/delete removed, {frees_added} added"
        )
    if not added and not removed:
        return Check("fail", "empty diff")
    return Check("pass", f"{len(paths)} file(s), +{len(added)}/-{len(removed)}")


def patched_check(exit_code: int, timed_out: bool, report: str, target_kind: str) -> Check:
    findings = parse_report(report)
    if findings:
        p = primary(findings)
        assert p is not None
        if p.kind == target_kind or any(f.kind == target_kind for f in findings):
            return Check("fail", f"still_crashes: {p.kind} at {p.location}")
        return Check("fail", f"new_{p.kind}: {p.summary[:100]} at {p.location}")
    if timed_out:
        return Check("inconclusive", "timeout")
    if exit_code != 0:
        return Check("inconclusive", f"exit {exit_code} without a parsable sanitizer report")
    return Check("pass", "no sanitizer report, exit 0")


def decide(checks: dict[str, Check]) -> str:
    def st(name: str) -> str:
        return checks[name].status if name in checks else "skipped"

    if st("unpatched_trips") != "pass":
        return "inconclusive:unpatched_does_not_trip"
    if st("diff_scope") == "fail":
        return "rejected:diff_scope"
    if st("build") == "fail":
        return "build_failed"
    patched = checks.get("patched")
    if patched is None or patched.status == "inconclusive":
        return f"inconclusive:{patched.detail if patched else 'not_run'}"
    if patched.status == "fail":
        return "rejected:" + patched.detail.split(":", 1)[0]
    if "fail" in (st("tests"), st("behavior")):
        return "silenced_only"
    if "inconclusive" in (st("tests"), st("behavior")):
        return "inconclusive:tests"
    return "verified"


def behavior_check(cwe: str, before: str, after: str) -> Check:
    if cwe == "CWE-401":
        return (
            Check("pass", "stdout identical")
            if before == after
            else Check("fail", f"stdout changed ({len(before)} -> {len(after)} bytes)")
        )
    # The unpatched run stops at the error; everything it printed before must still appear.
    return (
        Check("pass", "stdout keeps the pre-crash output")
        if after.startswith(before)
        else Check("fail", "stdout lost output printed before the crash point")
    )


def split(stdout: str) -> dict[str, str]:
    parts = re.split(rf"^{re.escape(MARK)} (\S+)\n", stdout, flags=re.M)
    return {parts[i]: parts[i + 1] for i in range(1, len(parts) - 1, 2)}


# ------------------------------------------------------------------------------- suites
class JulietGate:
    def __init__(self, case: JulietCase, runner: LocalDockerRunner, baseline: ImageRef) -> None:
        self.case, self.runner, self.baseline = case, runner, baseline
        self.unpatched_stdout = ""

    def _script(self, good: bool) -> str:
        d = self.case.data
        lines = [
            f"( {d['build_cmd_bad']} ) > out_b.log 2>&1; echo $? > rc_build",
            f"( {d['run_cmd_bad']} ) > out_run 2> err_run; echo $? > rc_run",
        ]
        if not good:
            # Behavior reference: LSan and ASan exit without flushing stdio, so the sanitizer
            # run's stdout is truncated. Leaks off + unbuffered stdout keeps what was printed.
            lines.append(
                f"( ASAN_OPTIONS=detect_leaks=0 stdbuf -o0 {d['run_cmd_bad']} ) > out_ref 2>/dev/null"
            )
        if good:
            lines += [
                f"( {d['build_cmd_good']} ) > out_bg.log 2>&1; echo $? > rc_build_good",
                f"( {d['run_cmd_good']} ) > /dev/null 2> err_good; echo $? > rc_good",
            ]
        for name in ("rc_build", "rc_run", "out_run", "err_run", "out_b.log") + (
            ("rc_build_good", "rc_good", "err_good") if good else ("out_ref",)
        ):
            lines.append(f"echo '{MARK} {name}'; cat {name} 2>/dev/null")
        return "\n".join(lines)

    def _run(self, files: dict[str, str] | None, good: bool) -> tuple[dict[str, str], Any]:
        res = self.runner.run(
            self.baseline,
            self._script(good),
            files={f"case/{k}": v.encode() for k, v in (files or {}).items()},
            env=self.case.data["env"],
            cwd="/work",
            network=False,
            timeout_s=300,
        )
        return split(res.stdout), res

    def unpatched(self) -> Check:
        sec, _ = self._run(None, good=False)
        self.unpatched_stdout = sec.get("out_ref", "")
        if sec.get("rc_build", "").strip() != "0":
            return Check("fail", "unpatched build failed")
        p = primary(parse_report(sec.get("err_run", "")))
        if p is None or p.kind != self.case.data["expected_kind"]:
            return Check("fail", f"unpatched run: {p.kind if p else 'no report'}")
        return Check(
            "pass", f"{p.kind} at {p.location}; reference stdout {len(self.unpatched_stdout)} bytes"
        )

    def candidate(self, cand: dict[str, Any], checks: dict[str, Check]) -> str:
        sec, res = self._run(cand["files"], good=True)
        if sec.get("rc_build", "").strip() != "0":
            checks["build"] = Check("fail", sec.get("out_b.log", "")[-600:])
            return ""
        checks["build"] = Check("pass")
        rc = int(sec.get("rc_run", "-1").strip() or -1)
        report = sec.get("err_run", "")
        checks["patched"] = patched_check(
            rc, rc == 124 or res.timed_out, report, self.case.data["expected_kind"]
        )
        good = parse_report(sec.get("err_good", ""))
        bad_good = [
            f.kind for f in good if self.case.data["expected_kind"] == "leak" or f.kind != "leak"
        ]
        if sec.get("rc_build_good", "").strip() != "0":
            checks["tests"] = Check("fail", "good-only build failed")
        else:
            checks["tests"] = (
                Check("fail", f"good path now reports {bad_good}")
                if bad_good
                else Check("pass", "good-only build clean")
            )
        checks["behavior"] = behavior_check(
            self.case.data["cwe"], self.unpatched_stdout, sec.get("out_run", "")
        )
        return report


class ArvoGate:
    def __init__(self, case: ArvoCase, runner: LocalDockerRunner, baseline: ImageRef) -> None:
        self.case, self.runner, self.baseline = case, runner, baseline
        self.tests_baseline: Check | None = None

    def unpatched(self) -> Check:
        tests = self.case.tests_cmd
        if tests:
            # A suite that already fails on the unpatched build cannot judge a patch.
            t = self.runner.run(
                self.baseline,
                f"( {tests} ) > /tmp/t.log 2>&1; rc=$?; tail -40 /tmp/t.log; exit $rc",
                env=BUILD_ENV,
                cwd=self.case.workdir,
                timeout_s=3600,
                network=False,
            )
            self.tests_baseline = Check("pass" if t.exit_code == 0 else "fail", t.stdout[-600:])
        res = self.runner.run(
            self.baseline, "arvo", cwd=self.case.workdir, timeout_s=300, network=False
        )
        p = primary(parse_report(res.stderr + res.stdout))
        want = self.case.finding.get("kind")
        if p is None or p.kind != want:
            return Check("fail", f"unpatched run: {p.kind if p else 'no report'} (expected {want})")
        return Check("pass", f"{p.kind} at {p.location}")

    def candidate(self, cand: dict[str, Any], checks: dict[str, Check]) -> str:
        tests = self.case.tests_cmd
        script = [
            "arvo compile > /tmp/compile.log 2>&1; echo $? > /tmp/rc_build",
            "if [ $(cat /tmp/rc_build) = 0 ]; then arvo > /tmp/out_run 2> /tmp/err_run; "
            "echo $? > /tmp/rc_run; fi",
        ]
        if tests:
            script.append(
                f"if [ $(cat /tmp/rc_run 2>/dev/null) = 0 ]; then ( {tests} ) > /tmp/tests.log 2>&1; "
                "echo $? > /tmp/rc_tests; fi"
            )
        for name in (
            "rc_build",
            "rc_run",
            "err_run",
            "out_run",
            "rc_tests",
            "tests.log",
            "compile.log",
        ):
            script.append(f"echo '{MARK} {name}'; tail -c 20000 /tmp/{name} 2>/dev/null")
        res = self.runner.run(
            self.baseline,
            "\n".join(script),
            files={k: v.encode() for k, v in cand["files"].items()},
            env=BUILD_ENV,
            cwd=self.case.workdir,
            timeout_s=3600,
            network=False,
        )
        sec = split(res.stdout)
        if sec.get("rc_build", "").strip() != "0":
            checks["build"] = Check("fail", sec.get("compile.log", "")[-800:])
            return ""
        checks["build"] = Check("pass")
        rc_raw = sec.get("rc_run", "").strip()
        report = sec.get("err_run", "") + sec.get("out_run", "")
        checks["patched"] = patched_check(
            int(rc_raw) if rc_raw else -1, res.timed_out, report, self.case.finding.get("kind", "")
        )
        if tests is None:
            checks["tests"] = Check("skipped", "no runnable project test suite in the image")
        elif self.tests_baseline is not None and self.tests_baseline.status != "pass":
            checks["tests"] = Check("skipped", "suite fails on the unpatched baseline too")
        elif checks["patched"].status == "pass":
            rc_t = sec.get("rc_tests", "").strip()
            checks["tests"] = Check(
                "pass" if rc_t == "0" else "fail", sec.get("tests.log", "")[-800:]
            )
        return report


def run_gate(
    case_id: str,
    baseline: ImageRef,
    candidates: list[dict[str, Any]],
    workdir: str | None,
    finding: dict[str, Any] | None,
) -> dict[str, Any]:
    runner = LocalDockerRunner(memory="4g", cpus=2)
    t0 = time.monotonic()
    if case_id.isdigit():
        case = ArvoCase.load(case_id)
        case.workdir = workdir or case.workdir
        case.finding = finding or {}
        gate: JulietGate | ArvoGate = ArvoGate(case, runner, baseline)
        allowed, src_root = None, case.src_root
    else:
        jcase = JulietCase.load(case_id)
        gate = JulietGate(jcase, runner, baseline)
        allowed, src_root = set(jcase.source_files()), None
    kind = (finding or {}).get("kind") or getattr(gate.case, "finding", {}).get("kind", "")
    unpatched = gate.unpatched()
    results = []
    for cand in candidates:
        c0 = time.monotonic()
        checks: dict[str, Check] = {"unpatched_trips": unpatched}
        checks["diff_scope"] = diff_scope(
            cand["diff"],
            list(cand["files"]),
            allowed,
            src_root,
            cand.get("strategy", "other"),
            kind,
        )
        report = ""
        if unpatched.status == "pass" and checks["diff_scope"].status == "pass":
            report = gate.candidate(cand, checks)
        r = GateResult(
            cand["hypothesis_id"],
            cand["worker_index"],
            decide(checks),
            checks,
            report[-4000:],
            round(time.monotonic() - c0, 2),
        )
        results.append(r.to_dict())
    return {
        "case": case_id,
        "baseline": baseline.ref,
        "gate_version": "v0",
        "unpatched": unpatched.to_dict(),
        "tests_baseline": tb.to_dict() if (tb := getattr(gate, "tests_baseline", None)) else None,
        "results": results,
        "elapsed_s": round(time.monotonic() - t0, 2),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--workdir")
    ap.add_argument("--candidates", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    payload = json.loads(args.candidates.read_text())
    out = run_gate(
        args.case,
        ImageRef("docker", args.baseline),
        payload["candidates"],
        args.workdir,
        payload.get("finding"),
    )
    args.out.write_text(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
