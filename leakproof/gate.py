"""The evidence gate (v1). Runs as its own process; workers never import this module.

    python -m leakproof.gate --case ID --baseline IMAGE [--workdir DIR] --candidates C.json --out V.json

Every check starts from the baseline checkpoint in a fresh container with the network off:
  1 unpatched_trips  the unpatched build still trips under the same flags (D-0020)
  2 patched          patched build + PoC: no sanitizer report (tool error = inconclusive, D-0028)
  3 tests            project tests pass under ASan (Juliet: good-only build stays clean)
  3b behavior        Juliet: program output unchanged (leaks) / not truncated (crashes)
  4 diff_scope       only editable source files; no sanitizer, flag or exit tricks; no removed
                     free() without a replacement unless the defect is a double free
  compiled           ARVO: the harness binary changed, i.e. the patch is in what we test
  5 differential     ARVO: corpus before/after: same exit codes and stdout, no new report
  6 refuzz           ARVO: amplified PoC variants, then libFuzzer seeded with corpus + PoC
  7 safe_fix         ARVO: corpus under LeakSanitizer: no new leak / UAF / double free
  (5-7 live in leakproof/gate_fuzz.py; Juliet programs take no input, so they skip there)
Verdict: verified | silenced_only | rejected:<reason> | build_failed | inconclusive:<reason>
"""

from __future__ import annotations

import argparse
import base64
import json
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from leakproof import gate_cli as gc
from leakproof import gate_fuzz as gf
from leakproof.cases.arvo import ArvoCase
from leakproof.cases.juliet import JulietCase
from leakproof.cases.project import ProjectCase
from leakproof.findings import parse_report, primary
from leakproof.runner import ImageRef, LocalDockerRunner, get_runner

MARK = "@@LPGATE@@"
SOURCE_EXT = (".c", ".h", ".cc", ".cpp", ".cxx", ".hpp", ".hh", ".inc")
FORBIDDEN_DIRS = re.compile(
    r"/(tests?|testsuite|fuzz|fuzzing|fuzzers?|oss-?fuzz|harness(es)?|regress)/", re.I
)
HARNESS_ENTRY = "LLVMFuzzerTestOneInput"
REMOVED_FREE_DEFERRED = "removed_free_deferred"
BUILD_ERROR = re.compile(r"\berror\b|\bError \d|undefined reference|No rule to make", re.I)
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
    artifacts: list[str] = field(default_factory=list)
    amplification: dict[str, dict[str, str]] = field(default_factory=dict)
    evidence: dict[str, Any] = field(default_factory=dict)

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
    contents: dict[str, str] | None = None,
    defer_removed_free: bool = False,
) -> Check:
    for p in paths:
        if allowed is not None and p not in allowed:
            return Check("fail", f"edited {p}, not an editable source file")
        # The harness is part of the gate wherever it lives (`harnesses/`, `ossfuzz/`,
        # `src/pcre2_fuzzsupport.c`): judge by content, not only by directory name.
        if contents and HARNESS_ENTRY in contents.get(p, ""):
            return Check("fail", f"fuzz_harness_file: edited {p}, which defines the fuzz entry")
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
    removed_free = (
        frees_removed > frees_added and strategy != "remove_free" and kind != "double-free"
    )
    if removed_free and not defer_removed_free:
        return Check(
            "fail", f"removed_free: {frees_removed} free/delete removed, {frees_added} added"
        )
    if not added and not removed:
        return Check("fail", "empty diff")
    detail = f"{len(paths)} file(s), +{len(added)}/-{len(removed)}"
    if removed_free:
        # ARVO (D-0046): an ownership transfer legitimately drops a free (libzip 42520377);
        # whether it leaks is measured instead - the PoC must then be clean under LSan.
        detail = f"{REMOVED_FREE_DEFERRED}: {frees_removed} removed, {frees_added} added; " + detail
    return Check("pass", detail)


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
    if st("compiled") == "inconclusive":
        return "inconclusive:patch_not_compiled"
    patched = checks.get("patched")
    if patched is None or patched.status == "inconclusive":
        return f"inconclusive:{patched.detail if patched else 'not_run'}"
    if patched.status == "fail":
        return "rejected:" + patched.detail.split(":", 1)[0]
    if st("refuzz") == "fail" and checks["refuzz"].detail.startswith("same bug"):
        return "rejected:refuzz_same_bug"
    for name, reason in (
        ("refuzz", "refuzz_new_crash"),
        ("differential", "differential"),
        ("safe_fix", "safe_fix"),
    ):
        if st(name) == "fail":
            return f"rejected:{reason}"
    for name in ("refuzz", "differential", "safe_fix"):
        if st(name) == "inconclusive":
            return f"inconclusive:{name}"
    if "fail" in (st("tests"), st("behavior")):
        return "silenced_only"
    if "inconclusive" in (st("tests"), st("behavior")):
        return "inconclusive:tests"
    if st("adversary") == "fail":
        # D-0079: only a machine-confirmed input (sanitizer report or output difference).
        return "rejected:" + checks["adversary"].detail.split(":", 1)[0]
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


# One line per test result: automake (`PASS: tests/x`) and CUnit (`Test: name ...passed`).
TEST_LINES = "'^(PASS|FAIL|XFAIL|XPASS|ERROR): |^Suite: |Test: .*[.]{3}(passed|FAILED)'"
# The whole rest of the line names the test: automake prints a path, toybox a sentence.
_AUTOMAKE = re.compile(r"^(PASS|FAIL|XFAIL|XPASS|ERROR): (.+?)\s*$")
_CUNIT_SUITE = re.compile(r"^Suite: (.+)")
_CUNIT_TEST = re.compile(r"Test: (.+?) \.\.\.(passed|FAILED)")


def test_results(text: str) -> dict[str, bool]:
    """{test name: passed} from a suite's output (automake or CUnit)."""
    out: dict[str, bool] = {}
    suite = ""
    for line in text.splitlines():
        if m := _AUTOMAKE.match(line):
            out[m.group(2)] = m.group(1) in ("PASS", "XFAIL")
        elif m := _CUNIT_SUITE.match(line.strip()):
            suite = m.group(1).strip()
        elif m := _CUNIT_TEST.search(line):
            out[f"{suite}/{m.group(1)}"] = m.group(2) == "passed"
    return out


def compare_tests(base: dict[str, bool], patched: dict[str, bool]) -> Check:
    """A suite that fails on the baseline: every test that passes there must still pass."""
    broken = sorted(n for n, ok in base.items() if ok and not patched.get(n, False))
    already = sum(not ok for ok in base.values())
    note = f"{sum(base.values())} tests pass on the baseline ({already} already failing there)"
    if broken:
        missing = sum(n not in patched for n in broken)
        return Check(
            "fail",
            f"{len(broken)} test(s) that pass on the baseline fail now"
            + (f" or did not run ({missing})" if missing else "")
            + f": {', '.join(broken[:5])}; {note}",
        )
    return Check("pass", f"all {note} still pass")


def split(stdout: str) -> dict[str, str]:
    # The separator carries its own leading newline (printf '\n@@LPGATE@@ name\n'), so a file
    # without a trailing newline cannot swallow the next marker; contents stay byte-exact.
    parts = re.split(rf"\n{re.escape(MARK)} (\S+)\n", stdout)
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
            lines.append(f"printf '\n{MARK} {name}\n'; cat {name} 2>/dev/null")
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
        for name in ("differential", "refuzz", "safe_fix"):
            checks[name] = Check("skipped", "Juliet programs take no input (no fuzz harness)")
        return report


class ArvoGate:
    def __init__(
        self,
        case: ArvoCase,
        runner: LocalDockerRunner,
        baseline: ImageRef,
        artifacts: Path | None = None,
        fuzz_seconds: int = 90,
        reference: ImageRef | None = None,
    ) -> None:
        self.case, self.runner, self.baseline = case, runner, baseline
        # The developer's fix built on the baseline (calibration / ARVO only): a second
        # reference when attributing a refuzz crash. Never shown to workers.
        self.reference = reference
        self.tests_baseline: Check | None = None
        self.tests_baseline_results: dict[str, bool] = {}
        # Suite hooks (ArvoCase, ProjectCase): harness for checks 5-7 (None = skip them),
        # artifact whose hash proves the patch was compiled, reproduce and build commands.
        self.harness = case.harness_path
        self.artifact = case.artifact_path
        self.harness_hash = ""
        self.artifacts, self.fuzz_seconds = artifacts, fuzz_seconds
        self.fuzz_seed = 1  # libFuzzer -seed; a repair round re-gates with a fresh one
        self.poc = b""
        self.corpus_tgz = b""
        self.corpus_source = ""
        self.base_diff: dict[str, gf.Row] = {}
        self.base_leak: dict[str, gf.Row] = {}
        self.amp: list[tuple[str, bytes]] = []
        self.ref_leak: dict[str, gf.Row] | None = None
        # No harness but a PoC input (bring-your-own projects): generated inputs (D-0078).
        self.cli_inputs: list[tuple[str, bytes]] = []
        self.cli_base: gc.Run | None = None

    def unpatched(self) -> Check:
        tests = self.case.tests_cmd
        if tests:
            # A suite that already fails on the unpatched build judges a patch per test: the
            # tests that pass on the baseline must still pass (D-0073).
            t = self.runner.run(
                self.baseline,
                f"( {tests} ) > /tmp/t.log 2>&1; rc=$?; grep -E {TEST_LINES} /tmp/t.log; "
                f"printf '\n{MARK} tail\n'; tail -40 /tmp/t.log; exit $rc",
                env=self.case.build_env,
                cwd=self.case.workdir,
                timeout_s=3600,
                network=False,
            )
            head, _, tail = t.stdout.partition(f"\n{MARK} tail\n")
            self.tests_baseline = Check("pass" if t.exit_code == 0 else "fail", tail[-600:])
            self.tests_baseline_results = test_results(head)
        hash_cmd = f"md5sum {self.artifact} > /tmp/hash; " if self.artifact else ": > /tmp/hash; "
        res = self.runner.run(
            self.baseline,
            hash_cmd + f"{self.case.reproduce_cmd}; rc=$?; cat /tmp/hash; exit $rc",
            env=getattr(self.case, "reproduce_env", None),
            cwd=self.case.workdir,
            timeout_s=300,
            network=False,
        )
        self.harness_hash = (
            res.stdout.strip().split("\n")[-1].split(" ")[0] if self.artifact else ""
        )
        p = primary(parse_report(res.stderr + res.stdout))
        want = self.case.finding.get("kind")
        if p is None or p.kind != want:
            return Check("fail", f"unpatched run: {p.kind if p else 'no report'} (expected {want})")
        if self.harness is None:
            note = self._cli_baseline()
            return Check("pass", f"{p.kind} at {p.location}; {note}")
        self._baseline_corpus()
        return Check(
            "pass",
            f"{p.kind} at {p.location}; corpus {len(self.base_diff)} inputs "
            f"({self.corpus_source}); {len(self.amp)} amplified PoC variants",
        )

    def _cli_baseline(self) -> str:
        """Checks 5-7 without a harness: generate inputs from /tmp/poc, run them unpatched."""
        if not isinstance(self.case, ProjectCase) or not self.case.cfg.get("poc"):
            return "no fuzz harness and no PoC input file: checks 5-7 skipped"
        poc = self.runner.read(self.baseline, "/tmp/poc")
        self.cli_inputs = gc.generate(poc)
        res = self.runner.run(
            self.baseline,
            gc.script([n for n, _ in self.cli_inputs], self.case.reproduce_cmd),
            files=gc.files(self.cli_inputs, self.case.reproduce_cmd),
            env=self.case.build_env | (getattr(self.case, "reproduce_env", None) or {}),
            cwd=self.case.workdir,
            timeout_s=3600,
            network=False,
        )
        self.cli_base = gc.Run.parse(split(res.stdout))
        crashing = sum(1 for r in self.cli_base.rows.values() if r.sig)
        return (
            f"no fuzz harness: {len(self.cli_inputs)} inputs generated from the PoC "
            f"({crashing} crash unpatched)"
        )

    def _baseline_corpus(self) -> None:
        h = self.harness
        script = gf.discover_script(self.case.project, h)
        script += gf.corpus_run_script(h, gf.ASAN_DIFF, "corpus_diff")
        script += gf.corpus_run_script(h, gf.ASAN_LEAK, "corpus_leak", "-detect_leaks=1")
        res = self.runner.run(
            self.baseline, script, cwd=self.case.workdir, timeout_s=3600, network=False
        )
        sec = split(res.stdout)
        self.corpus_source = sec.get("corpus_source", "").strip()
        self.corpus_tgz = base64.b64decode(sec.get("corpus_b64", "").strip())
        self.poc = base64.b64decode(sec.get("poc_b64", "").strip())
        self.base_diff = gf.parse_rows(sec.get("corpus_diff", ""))
        self.base_leak = gf.parse_rows(sec.get("corpus_leak", ""))
        self.amp = gf.amplify(self.poc)
        if self.reference is not None:
            # The developer fix's own leak profile: what safe_fix compares candidates against.
            res = self.runner.run(
                self.reference,
                (gf.unpack_corpus_cmd() if self.corpus_tgz else f"mkdir -p {gf.LP}/corpus")
                + gf.corpus_run_script(h, gf.ASAN_LEAK, "corpus_leak", "-detect_leaks=1"),
                files={f"{gf.LP}/corpus.tgz": self.corpus_tgz} if self.corpus_tgz else None,
                cwd=self.case.workdir,
                timeout_s=3600,
                network=False,
            )
            self.ref_leak = gf.parse_rows(split(res.stdout).get("corpus_leak", ""))

    def _fuzz_files(self) -> dict[str, bytes]:
        files = {f"{gf.LP}/amp/{n}": d for n, d in self.amp}
        if self.corpus_tgz:
            files[f"{gf.LP}/corpus.tgz"] = self.corpus_tgz
        return files

    def _fuzz_script(self) -> str:
        # Seed libFuzzer only with corpus inputs the baseline runs cleanly, so a pre-existing
        # crash in the corpus cannot end the campaign at its first execution.
        clean = sorted(n for n, r in self.base_diff.items() if not r.sig and r.rc == "0")
        h = self.harness
        return "\n".join(
            [
                gf.unpack_corpus_cmd() if self.corpus_tgz else f"mkdir -p {gf.LP}/corpus",
                gf.corpus_run_script(h, gf.ASAN_DIFF, "corpus_diff"),
                gf.corpus_run_script(h, gf.ASAN_LEAK, "corpus_leak", "-detect_leaks=1", 3),
                gf.poc_leak_script(h),
                gf.refuzz_script(
                    h,
                    [n for n, _ in self.amp],
                    clean,
                    self.fuzz_seconds,
                    max(8 * len(self.poc), 4096),
                    self.fuzz_seed,
                ),
            ]
        )

    def probe(self, image: ImageRef, data: bytes) -> str:
        """Run one input through `image`'s harness; the sanitizer report ('' if clean)."""
        res = self.runner.run(
            image,
            gf.confirm_script(self.harness),
            files={f"{gf.LP}/confirm/input": data},
            cwd=self.case.workdir,
            timeout_s=300,
            network=False,
        )
        return split(res.stdout).get("confirm", "")

    def _judge_fuzz(
        self, sec: dict[str, str], cand: dict[str, Any], checks: dict[str, Check]
    ) -> list[str]:
        """Checks 5-7 from the candidate run's sections; returns saved artifact paths."""
        st, detail = gf.differential(self.base_diff, gf.parse_rows(sec.get("corpus_diff", "")))
        checks["differential"] = Check(st, detail)
        patched_diff = gf.parse_rows(sec.get("corpus_diff", ""))
        patched_leak = gf.parse_rows(sec.get("corpus_leak", ""))
        st, detail = gf.safe_fix(self.base_leak, patched_leak, self.ref_leak)
        poc_leak = sec.get("poc_leak", "").strip()
        if checks["diff_scope"].detail.startswith(REMOVED_FREE_DEFERRED) and poc_leak:
            st, detail = "fail", f"removed a free and the PoC now reports {poc_leak}; " + detail
        checks["safe_fix"] = Check(st, detail)
        cand["_evidence"] = {
            "corpus_rows_differing": {
                n: {
                    "baseline": [b.rc, b.sig, self.base_leak.get(n, gf.Row("", "", "")).sig],
                    "patched": [p.rc, p.sig, patched_leak.get(n, gf.Row("", "", "")).sig],
                }
                for n, b in self.base_diff.items()
                if (p := patched_diff.get(n, gf.Row("?", "?", "?"))) != b
                or self.base_leak.get(n) != patched_leak.get(n)
            }
            if len(self.base_diff) and patched_diff
            else {},
            "poc_under_lsan": poc_leak or "clean",
            "poc_leak_report": sec.get("poc_leak_report", "")[:4000] if poc_leak else "",
            "leak_reports": {
                k.split("_rep_", 1)[1]: v
                for k, v in sec.items()
                if k.startswith("corpus_leak_rep_")
            },
        }
        rows = cand["_evidence"]["corpus_rows_differing"]
        if len(rows) > 20:
            cand["_evidence"]["corpus_rows_differing"] = dict(list(rows.items())[:20])
        amp_rows = gf.parse_amp(sec.get("amp_res", ""))
        cand["_amplification"] = {n: {"rc": rc, "sig": sig} for n, (rc, sig) in amp_rows.items()}
        crash: tuple[str, bytes, str, str] | None = None  # source, input, report, rc
        for name, data in self.amp:
            rc, sig = amp_rows.get(name, ("0", ""))
            if rc != "0" or sig:
                crash = (f"amplification:{name}", data, sec.get("amp_report", ""), rc)
                break
        fuzz_note = ""
        if crash is None:
            rc = sec.get("fuzz_rc", "").strip()
            runs = gf.summary(sec.get("fuzz_stats", "")).get("number_of_executed_units", "?")
            fuzz_note = f"libFuzzer {self.fuzz_seconds}s rc={rc or '?'} runs={runs}"
            name, _, data = sec.get("fuzz_artifact", "").strip().partition(" ")
            if data:
                crash = (f"fuzzing:{name}", base64.b64decode(data), sec.get("fuzz_report", ""), rc)
            elif not rc:
                checks["refuzz"] = Check("inconclusive", "libFuzzer did not run")
                return []
            elif rc != "0":
                checks["refuzz"] = Check("inconclusive", f"{fuzz_note} without an artifact")
                return []
            elif not runs.isdigit() or int(runs) == 0:
                # Exit 0 with no execution count: not a libFuzzer binary, nothing was fuzzed.
                checks["refuzz"] = Check("inconclusive", f"{fuzz_note}: no executions reported")
                return []
            else:
                checks["refuzz"] = Check(
                    "pass", f"{len(self.amp)} amplified variants clean; {fuzz_note}, no crash"
                )
                return []
        source, data, report, rc = crash
        key = gf.crash_key(report, rc) or ("unknown", "")
        base_report = self.probe(self.baseline, data)
        ref_report = self.probe(self.reference, data) if self.reference else None
        blame, why = gf.attribute(key, base_report, gf.finding_site(self.case.finding), ref_report)
        detail = f"{key[0]} at {key[1] or '?'} from {source} ({len(data)} bytes); {why}"
        if fuzz_note:
            detail += f"; {fuzz_note}"
        checks["refuzz"] = Check("fail" if blame else "pass", detail)
        if self.artifacts is None:
            return []
        self.artifacts.mkdir(parents=True, exist_ok=True)
        tag = re.sub(r"[^A-Za-z0-9_.-]", "_", source)
        path = self.artifacts / f"{cand['hypothesis_id']}_w{cand['worker_index']}_{tag}.bin"
        path.write_bytes(data)
        path.with_suffix(".log").write_text(report, encoding="utf-8")
        return [str(path), str(path.with_suffix(".log"))]

    def adversary(self, cand: dict[str, Any], model: str, client: Any) -> tuple[Check, list[str]]:
        """D-0079: `model` proposes inputs against this one candidate; the machine judges them.
        Runs only on a candidate every other check verified. Never raises: a model failure or
        a build failure is a skipped check, which leaves the verdict alone."""
        from leakproof import adversary as adv

        try:
            poc = self.runner.read(self.baseline, "/tmp/poc")
        except Exception:  # noqa: BLE001 - no PoC file: the prompt says so
            poc = b""
        originals = {}
        for path in cand["files"]:
            try:
                originals[path] = self.runner.read(self.baseline, path).decode("utf-8", "replace")
            except Exception:  # noqa: BLE001 - a new file has no original
                originals[path] = ""
        report = json.dumps(self.case.finding)[:4000]
        text = adv.prompt(report, adv.how(self.case), poc, originals, cand["files"], cand["diff"])
        # Super falls back to Ultra once when it gives no usable input (D-0080).
        inputs, model, notes = adv.attack_with_fallback(client, model, text)
        if not inputs:
            return Check("skipped", f"no inputs ({'; '.join(notes)[:200]})"), []
        n_in = f"{model}, {len(inputs)} inputs" + (" (fallback)" if notes else "")
        try:
            base = adv.run_inputs(self.runner, self.case, self.baseline, inputs)
            pat = adv.run_inputs(self.runner, self.case, self.baseline, inputs, cand["files"])
            ref = (
                adv.run_inputs(self.runner, self.case, self.reference, inputs)
                if self.reference
                else None
            )
        except RuntimeError as exc:
            return Check("skipped", f"{model}: {str(exc)[:200]}"), []
        target = (gf._norm(self.case.finding.get("kind", "")), gf.finding_site(self.case.finding))
        verdict, detail, rows = adv.judge(
            base, pat, ref, target, self.case.finding.get("location") or ""
        )
        saved: list[str] = []
        if self.artifacts is not None:
            d = self.artifacts / f"{cand['hypothesis_id']}_w{cand['worker_index']}_adversary"
            d.mkdir(parents=True, exist_ok=True)
            for i in inputs:
                (d / i["name"]).write_bytes(i["data"])
                saved.append(str(d / i["name"]))
            reasons = {i["name"]: (i["expect"], i["reason"]) for i in inputs}
            for r in rows:
                r["expect"], r["reason"] = reasons.get(r["input"], ("", ""))
                r["report"] = pat.reports.get(r["input"], "")[:3000]
            (d / "adversary.json").write_text(
                json.dumps({"model": model, "fallback_notes": notes, "rows": rows}, indent=1)
            )
        if verdict in ("pass", "inconclusive"):
            return Check("pass" if verdict == "pass" else "skipped", f"{n_in}: {detail}"), saved
        return Check("fail", f"{verdict}: {n_in}: {detail}"), saved

    def candidate(self, cand: dict[str, Any], checks: dict[str, Check]) -> str:
        tests = self.case.tests_cmd
        hash_cmd = f"md5sum {self.artifact} > /tmp/hash 2>&1" if self.artifact else ": > /tmp/hash"
        script = [
            f"{{ {self.case.gate_build_cmd(cand['files'])} ; }} > /tmp/compile.log 2>&1; "
            f"echo $? > /tmp/rc_build; {hash_cmd}",
            f"if [ $(cat /tmp/rc_build) = 0 ]; then {self.case.reproduce_cmd} > /tmp/out_run "
            "2> /tmp/err_run; echo $? > /tmp/rc_run; fi",
        ]
        if tests:
            script.append(
                f"if [ $(cat /tmp/rc_run 2>/dev/null) = 0 ]; then ( {tests} ) > /tmp/tests.log 2>&1; "
                f"echo $? > /tmp/rc_tests; grep -E {TEST_LINES} /tmp/tests.log > /tmp/tests.res; fi"
            )
        # Checks 5-7 only judge a patch that already survives its own PoC.
        if self.harness is not None:
            script.append(
                "if [ $(cat /tmp/rc_run 2>/dev/null) = 0 ]; then\n" + self._fuzz_script() + "\nfi"
            )
        elif self.cli_inputs:
            # The reproducer may exit non-zero on a rejected input; the build is the gate here.
            script.append(
                "if [ $(cat /tmp/rc_build) = 0 ]; then\n"
                + gc.script([n for n, _ in self.cli_inputs], self.case.reproduce_cmd)
                + "\nfi"
            )
        for name in (
            "rc_build",
            "rc_run",
            "err_run",
            "out_run",
            "rc_tests",
            "tests.res",
            "tests.log",
            "compile.log",
            "hash",
        ):
            script.append(f"printf '\n{MARK} {name}\n'; tail -c 20000 /tmp/{name} 2>/dev/null")
        res = self.runner.run(
            self.baseline,
            "\n".join(script),
            files={k: v.encode() for k, v in cand["files"].items()}
            | (self._fuzz_files() if self.harness is not None else {})
            | (gc.files(self.cli_inputs, self.case.reproduce_cmd) if self.cli_inputs else {}),
            env=self.case.build_env | (getattr(self.case, "reproduce_env", None) or {}),
            cwd=self.case.workdir,
            timeout_s=3600,
            network=False,
        )
        sec = split(res.stdout)
        if sec.get("rc_build", "").strip() != "0":
            log = sec.get("compile.log", "")
            # The tail of an OSS-Fuzz build is environment noise; the compiler errors say why.
            errors = [ln for ln in log.splitlines() if BUILD_ERROR.search(ln)][:15]
            checks["build"] = Check("fail", "\n".join(errors)[:1500] + "\n...\n" + log[-400:])
            if self.artifacts is not None:
                self.artifacts.mkdir(parents=True, exist_ok=True)
                name = f"{cand['hypothesis_id']}_w{cand['worker_index']}_compile.log"
                (self.artifacts / name).write_text(log, encoding="utf-8")
            return ""
        checks["build"] = Check("pass")
        # Proof the patch is in the binary under test: an unchanged harness means the build
        # system skipped the edited files, and any result from it says nothing about the patch.
        new_hash = sec.get("hash", "").split(" ")[0].strip()
        if self.artifact is None:
            checks["compiled"] = Check("skipped", "no build artifact configured to hash")
        elif not new_hash or new_hash == self.harness_hash:
            checks["compiled"] = Check(
                "inconclusive", f"harness unchanged ({new_hash or 'no hash'})"
            )
            return ""
        else:
            checks["compiled"] = Check("pass", f"harness {self.harness_hash[:8]} -> {new_hash[:8]}")
        rc_raw = sec.get("rc_run", "").strip()
        report = sec.get("err_run", "") + sec.get("out_run", "")
        checks["patched"] = patched_check(
            int(rc_raw) if rc_raw else -1, res.timed_out, report, self.case.finding.get("kind", "")
        )
        if tests is None:
            checks["tests"] = Check("skipped", "no runnable project test suite in the image")
        elif self.tests_baseline is not None and self.tests_baseline.status != "pass":
            base = self.tests_baseline_results
            if not any(base.values()):
                checks["tests"] = Check("skipped", "suite fails on the unpatched baseline too")
            elif checks["patched"].status == "pass":
                checks["tests"] = compare_tests(base, test_results(sec.get("tests.res", "")))
        elif checks["patched"].status == "pass":
            rc_t = sec.get("rc_tests", "").strip()
            checks["tests"] = Check(
                "pass" if rc_t == "0" else "fail", sec.get("tests.log", "")[-800:]
            )
        if checks["patched"].status == "pass" and self.harness is not None:
            cand["_artifacts"] = self._judge_fuzz(sec, cand, checks)
        elif self.harness is None and self.cli_base is not None:
            if checks["patched"].status == "pass":
                target = (
                    gf._norm(self.case.finding.get("kind", "")),
                    gf.finding_site(self.case.finding),
                )
                refuzz, diff = gc.judge(self.cli_base, gc.Run.parse(sec), target)
                checks["refuzz"] = Check(*refuzz)
                checks["differential"] = Check(*diff)
                checks["safe_fix"] = Check(
                    "pass" if refuzz[0] == "pass" else "skipped",
                    "LeakSanitizer was on for every generated input (leaks judged by refuzz)",
                )
        elif self.harness is None:
            for name in ("differential", "refuzz", "safe_fix"):
                checks[name] = Check("skipped", "no fuzz harness and no PoC input file")
        return report


def run_gate(
    case_id: str,
    baseline: ImageRef,
    candidates: list[dict[str, Any]],
    workdir: str | None,
    finding: dict[str, Any] | None,
    artifacts: Path | None = None,
    fuzz_seconds: int = 90,
    reference: ImageRef | None = None,
    runner_name: str = "docker",
    fuzz_seed: int = 1,
    adversary: str = "off",
    adversary_budget: float = 0.0,
) -> dict[str, Any]:
    # Every gate run has networking off whichever backend runs it (Docker --network=none,
    # Sandboxes networking.enabled=false).
    runner = (
        LocalDockerRunner(memory="4g", cpus=2)
        if runner_name == "docker"
        else get_runner(runner_name, run_id=f"gate:{case_id}")
    )
    t0 = time.monotonic()
    if case_id.isdigit() or case_id.startswith("project:"):
        case = ArvoCase.load(case_id) if case_id.isdigit() else ProjectCase.load(case_id)
        case.workdir = workdir or case.workdir
        case.finding = finding or {}
        gate: JulietGate | ArvoGate = ArvoGate(
            case, runner, baseline, artifacts, fuzz_seconds, reference
        )
        gate.fuzz_seed = fuzz_seed
        allowed, src_root = None, case.src_root
    else:
        jcase = JulietCase.load(case_id)
        gate = JulietGate(jcase, runner, baseline)
        allowed, src_root = set(jcase.source_files()), None
    kind = (finding or {}).get("kind") or getattr(gate.case, "finding", {}).get("kind", "")
    unpatched = gate.unpatched()
    results = []
    adv_client = None
    if adversary != "off" and isinstance(gate, ArvoGate) and adversary_budget > 0:
        # Gate-side model calls (D-0079): metered to the same ledger, capped by what is left of
        # the run's budget. Workers have finished; nothing here goes back to them.
        from leakproof.llm import CostLedger, LLMClient

        adv_client = LLMClient(
            ledger=CostLedger(budget=adversary_budget), run_id=f"gate-adversary:{case_id}"
        )
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
            cand["files"],
            # Only where the LSan checks that decide it run (a fuzz harness: ARVO, projects).
            defer_removed_free=src_root is not None and getattr(gate, "harness", None) is not None,
        )
        report = ""
        if unpatched.status == "pass" and checks["diff_scope"].status == "pass":
            report = gate.candidate(cand, checks)
        verdict = decide(checks)
        adv_saved: list[str] = []
        if verdict == "verified" and adv_client is not None:
            checks["adversary"], adv_saved = gate.adversary(cand, adversary, adv_client)
            verdict = decide(checks)
        r = GateResult(
            cand["hypothesis_id"],
            cand["worker_index"],
            verdict,
            checks,
            report[-4000:],
            round(time.monotonic() - c0, 2),
            cand.pop("_artifacts", []) + adv_saved,
            cand.pop("_amplification", {}),
            cand.pop("_evidence", {}),
        )
        results.append(r.to_dict())
    return {
        "case": case_id,
        "baseline": baseline.ref,
        "gate_version": "v1",
        "reference": reference.ref if reference else None,
        "unpatched": unpatched.to_dict(),
        "corpus": {
            "source": getattr(gate, "corpus_source", None),
            "inputs": len(getattr(gate, "base_diff", {})),
            "amplified_variants": [n for n, _ in getattr(gate, "amp", [])],
            "poc_bytes": len(poc := getattr(gate, "poc", b"")),
            "poc_b64": gf.b64(poc) if len(poc) <= 4096 else None,
            **gf.output_stats(getattr(gate, "base_diff", {})),
        },
        "tests_baseline": tb.to_dict() if (tb := getattr(gate, "tests_baseline", None)) else None,
        "results": results,
        "adversary": {
            "model": adversary if adv_client else "off",
            "usd": round(adv_client.ledger.spent, 6) if adv_client else 0.0,
        },
        "elapsed_s": round(time.monotonic() - t0, 2),
        "runner": runner_name,
        # Sandboxes: every saved run (parent image -> child image), for the lineage view.
        "lineage": getattr(runner, "lineage", None),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--workdir")
    ap.add_argument("--candidates", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--artifacts", type=Path, help="refuzz crash inputs (default: next to --out)")
    ap.add_argument("--fuzz-seconds", type=int, default=90)
    ap.add_argument("--reference", help="image with the developer's fix (refuzz attribution)")
    ap.add_argument("--runner", default="docker", choices=["docker", "sandboxes", "local"])
    ap.add_argument(
        "--fuzz-seed", type=int, default=1, help="libFuzzer -seed (repair rounds: fresh)"
    )
    ap.add_argument("--adversary", default="off", choices=["off", "super", "ultra"])
    ap.add_argument("--adversary-budget", type=float, default=0.0, help="USD for its calls")
    args = ap.parse_args()
    payload = json.loads(args.candidates.read_text())
    out = run_gate(
        args.case,
        ImageRef(args.runner, args.baseline),
        payload["candidates"],
        args.workdir,
        payload.get("finding"),
        args.artifacts or args.out.parent / "gate_artifacts",
        args.fuzz_seconds,
        ImageRef(args.runner, args.reference) if args.reference else None,
        args.runner,
        args.fuzz_seed,
        args.adversary,
        args.adversary_budget,
    )
    args.out.write_text(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
