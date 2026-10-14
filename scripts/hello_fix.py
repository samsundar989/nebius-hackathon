#!/usr/bin/env python3
"""E0 stretch (kickoff 3.8): one Juliet CWE-401 case fixed by Nemotron 3.5 Lightning.

No planner, no gate. Lightning gets the bad-path source (the `#ifndef OMITGOOD` block, which
contains the reference fixes, is stripped) plus the parsed finding, and returns a unified diff.
The diff is applied in a fresh run from the base image (network off); then bad-only is rebuilt
and re-run (must be sanitizer-clean) and good-only must still be free of the target flaw.
The worker never sees build flags, run commands, or the harness.

Usage: uv run python scripts/hello_fix.py [--case ID] [--thinking off|on]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

from leakproof.findings import parse_report, primary
from leakproof.llm import CostLedger, LLMClient
from leakproof.patching import PatchError, apply_hunks, parse_diff
from leakproof.runner import ImageRef, LocalDockerRunner

ROOT = Path(__file__).resolve().parent.parent
JULIET = Path.home() / ".cache" / "leakproof" / "juliet" / "C"
IMAGE = ImageRef("docker", "leakproof/cpp-sanitizers:e0")
SUPPORT = ["io.c", "std_testcase.h", "std_testcase_io.h", "std_thread.h"]

SYSTEM = (
    "You repair memory-safety defects in C/C++. You receive one source file and a sanitizer "
    "finding. Make the smallest change that removes the defect without changing behavior on "
    "valid inputs. Reply with ONLY a unified diff (---/+++ headers with a/ and b/ prefixes, "
    "@@ hunks with 3 lines of context). No explanation, no code fences."
)


def strip_good(source: str) -> str:
    """Drop the `#ifndef OMITGOOD ... #endif` block (it shows the fixes)."""
    start = source.find("#ifndef OMITGOOD")
    if start == -1:
        return source
    end = source.find("#endif /* OMITGOOD */", start)
    return source[:start] + (source[end + len("#endif /* OMITGOOD */") :] if end != -1 else "")


def extract_diff(text: str) -> str:
    fence = re.search(r"```(?:diff|patch)?\n(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    start = text.find("--- ")
    return text[start:].rstrip() + "\n" if start != -1 else ""


def touched_files(diff: str) -> list[str]:
    return [m.group(1) for m in re.finditer(r"^\+\+\+ b/(\S+)", diff, re.M)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default="CWE401_Memory_Leak__char_malloc_05")
    ap.add_argument("--thinking", choices=["off", "on"], default="off")
    ap.add_argument("--diff-from", type=Path, help="re-apply the diff from an earlier run JSON")
    args = ap.parse_args()

    case = json.loads((ROOT / "cases" / "juliet" / f"{args.case}.json").read_text())
    (src_name,) = [f for f in case["files"] if f.endswith((".c", ".cpp"))]
    source = (JULIET / case["dir"] / src_name).read_text()
    finding = case["finding"]
    prompt = (
        f"File: {src_name}\n\nSanitizer finding ({finding['tool']}): {finding['summary']}\n"
        f"Kind: {finding['kind']} ({finding['cwe_guess']})\n"
        f"Allocation site: {Path(finding['alloc_site'] or '').name}\n"
        "Stack (innermost first):\n"
        + "\n".join(
            f"  {f['function']} {Path(f['file']).name}:{f['line']}"
            for f in finding["frames"]
            if f.get("file") and "/work/" in f["file"]
        )
        + f"\n\n--- {src_name} ---\n{strip_good(source)}"
    )

    if args.diff_from:
        prior = json.loads(args.diff_from.read_text())
        diff, res = prior["diff"], None
    else:
        client = LLMClient(ledger=CostLedger(budget=0.25, ledger_cap=5.0), run_id="e0-hello-fix")
        res = client.chat(
            "lightning",
            [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
            purpose="hello_fix:patch",
            thinking=args.thinking == "on",
            max_tokens=8192,
        )
        diff = extract_diff(res.text)
    touched = touched_files(diff)
    scope_ok = touched == [src_name]

    patched, strategies, apply_error = None, [], None
    try:
        hunks = parse_diff(diff).get(src_name, [])
        if not hunks:
            raise PatchError(f"diff does not touch {src_name}")
        # Apply to the region the model was shown (everything before the stripped good block),
        # then splice the untouched good block back.
        cut = source.find("#ifndef OMITGOOD")
        head, rest = (source[:cut], source[cut:]) if cut != -1 else (source, "")
        patched_head, strategies = apply_hunks(head, hunks)
        patched = patched_head + rest
    except PatchError as exc:
        apply_error = str(exc)

    files: dict[str, bytes | Path] = {f"case/{f}": JULIET / case["dir"] / f for f in case["files"]}
    files["orig/" + src_name] = JULIET / case["dir"] / src_name
    if patched is not None:
        files[f"case/{src_name}"] = patched.encode()
    files.update({f"support/{f}": JULIET / "testcasesupport" / f for f in SUPPORT})
    files["fix.diff"] = diff.encode()
    script = "\n".join(
        [
            "mkdir -p bin",
            # Record whether GNU patch (strict, fuzz 3) would accept the diff as written.
            "cd orig && patch -p1 --dry-run --fuzz=3 < ../fix.diff > ../patch.log 2>&1; "
            "echo STRICT_RC=$?; cd ..; cat patch.log",
            f"( {case['build_cmd_bad']} ) > build_bad.log 2>&1 || {{ echo BUILD_BAD_FAILED; "
            "cat build_bad.log; exit 0; }",
            f"( {case['run_cmd_bad']} ) > /dev/null 2> bad.err; echo BAD_RC=$?",
            f"( {case['build_cmd_good']} ) > build_good.log 2>&1 || echo BUILD_GOOD_FAILED",
            f"( {case['run_cmd_good']} ) > /dev/null 2> good.err; echo GOOD_RC=$?",
            "echo @@BAD_ERR; cat bad.err; echo @@GOOD_ERR; cat good.err",
        ]
    )
    runner = LocalDockerRunner(memory="1536m", cpus=1)
    run = runner.run(IMAGE, script, files=files, env=case["env"], network=False, timeout_s=300)
    out = run.stdout
    bad_err = (
        out.split("@@BAD_ERR\n", 1)[-1].split("@@GOOD_ERR\n", 1)[0] if "@@BAD_ERR" in out else ""
    )
    good_err = out.split("@@GOOD_ERR\n", 1)[-1] if "@@GOOD_ERR" in out else ""
    rc = dict(re.findall(r"^(STRICT_RC|BAD_RC|GOOD_RC)=(\d+)$", out, re.M))
    bad_findings = parse_report(bad_err)
    good_findings = parse_report(good_err)
    patch_ok = patched is not None
    bad_clean = patch_ok and rc.get("BAD_RC") == "0" and not bad_findings
    good_ok = patch_ok and not [
        f for f in good_findings if f.kind != "leak" or case["cwe"] == "CWE-401"
    ]
    verdict = {
        "case": args.case,
        "model": res.model if res else prior["model"],
        "thinking": args.thinking if res else prior["thinking"],
        "diff_reused_from": str(args.diff_from) if args.diff_from else None,
        "latency_s": round(res.latency_s, 2) if res else None,
        "prompt_tokens": res.prompt_tokens if res else None,
        "completion_tokens": res.completion_tokens if res else None,
        "reasoning_tokens": res.reasoning_tokens if res else None,
        "finish_reason": res.finish_reason if res else None,
        "usd": round(res.usd, 6) if res else 0.0,
        "strict_patch_applies": rc.get("STRICT_RC") == "0" and bool(diff.strip()),
        "tolerant_apply_strategies": strategies,
        "apply_error": apply_error,
        "diff_scope_ok": scope_ok,
        "touched": touched,
        "patch_applied_tolerant": patch_ok,
        "bad_rc": rc.get("BAD_RC"),
        "bad_findings": [f.kind for f in bad_findings],
        "bad_clean": bad_clean,
        "good_still_clean": good_ok,
        "verified_smoke": scope_ok and bad_clean and good_ok,
        "diff": diff,
        "runner_stdout_tail": out[-1500:] if not bad_clean else "",
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    first = primary(bad_findings)
    if first:
        verdict["remaining_finding"] = first.summary
    path = ROOT / "runs" / f"hello_fix_{time.strftime('%Y%m%d_%H%M%S')}.json"
    path.write_text(json.dumps(verdict, indent=1))
    print(json.dumps({k: v for k, v in verdict.items() if k != "runner_stdout_tail"}, indent=1))
    return 0 if verdict["verified_smoke"] else 1


if __name__ == "__main__":
    sys.exit(main())
