"""`leakproof package`: turn a verified fix into what a maintainer receives (review #11 order 2).

    leakproof package RECORD.json [--candidate winner|HYP:IDX] [--author "Name <mail>"]
                      [--issue N] [--out DIR]
    leakproof package --gate-dir DIR --candidate ID [--record RECORD.json] ...

Writes DIR/SUBMISSION.md and DIR/0001-<subject>.patch (`git format-patch` form, `git am` applies
it). No model calls: the commit message is built from the run's own root-cause text, finding and
diff; the evidence table comes from the gate's checks, with a row for every check, including the
ones that did not run and why. The author stays a placeholder unless --author is given.
"""

from __future__ import annotations

import json
import re
import textwrap
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from leakproof.evidence import strength

CHECKS = [
    ("unpatched_trips", "the bug reproduces on the unpatched build"),
    ("diff_scope", "the diff touches only source files it may edit"),
    ("build", "the patched project builds"),
    ("compiled", "the patch is compiled into the binary under test (hash changed)"),
    ("patched", "the reproducer runs clean under the sanitizers"),
    ("tests", "the project's own tests pass"),
    ("behavior", "output unchanged on the reproducer"),
    ("differential", "corpus inputs: same exit status and output"),
    ("refuzz", "amplified / generated inputs and fuzzing find no crash from the patch"),
    ("safe_fix", "no new leak or use-after-free under LeakSanitizer"),
    ("adversary", "inputs a Nemotron model wrote to break this patch"),
]
PLACEHOLDER = "<your git identity>"


def repo_diff(diff: str) -> str:
    """Container paths (a/src/<project>/x) -> repository paths (a/x), with `diff --git` headers."""
    out = []
    for line in diff.splitlines():
        line = re.sub(r"^(--- a|\+\+\+ b)/src/[^/]+/", r"\1/", line)
        if line.startswith("--- a/"):
            path = line[6:].split("\t")[0]
            out.append(f"diff --git a/{path} b/{path}")
        out.append(line)
    return "\n".join(out) + "\n"


def diffstat(diff: str) -> str:
    files: dict[str, list[int]] = {}
    cur = None
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            cur = line[6:].split("\t")[0]
            files[cur] = [0, 0]
        elif cur and line.startswith("+") and not line.startswith("+++"):
            files[cur][0] += 1
        elif cur and line.startswith("-") and not line.startswith("---"):
            files[cur][1] += 1
    rows = [f" {f} | {a + d} {'+' * a}{'-' * d}" for f, (a, d) in files.items()]
    ins, dels = sum(v[0] for v in files.values()), sum(v[1] for v in files.values())
    rows.append(f" {len(files)} file(s) changed, {ins} insertion(s)(+), {dels} deletion(s)(-)")
    return "\n".join(rows)


def _site(finding: dict[str, Any]) -> tuple[str, str]:
    """(function, repo-relative file:line) of the defect."""
    func = ""
    for fr in finding.get("frames") or []:
        f = fr.get("file") or ""
        if f.startswith("/src/") and not f.startswith("/src/llvm-project/"):
            func = fr.get("function") or ""
            break
    loc = re.sub(r"^/src/[^/]+/", "", finding.get("location") or "")
    return func, loc


def commit_message(finding: dict[str, Any], root_cause: str, issue: str | None) -> str:
    """Subject (`<file>: fix <kind> in <function>()`), a 3-5 line body from the root cause."""
    func, loc = _site(finding)
    kind = finding.get("kind") or "memory error"
    stem = Path(loc.split(":")[0]).stem or "fix"
    subject = f"{stem}: fix {kind} in {func}()" if func else f"{stem}: fix {kind}"
    # Whole sentences only, up to ~4 lines of 72 columns (at least the first sentence).
    sentences = re.split(r"(?<=[.!?])\s+", " ".join(root_cause.split()))
    kept: list[str] = []
    for s in sentences:
        if kept and len(" ".join([*kept, s])) > 280:
            break
        kept.append(s)
    body = textwrap.wrap(" ".join(kept), 72)
    body.append(f"AddressSanitizer: {kind} at {loc}." if loc else f"Sanitizer: {kind}.")
    msg = subject + "\n\n" + "\n".join(body)
    if issue:
        msg += f"\n\nFixes #{issue.lstrip('#')}."
    return msg


def format_patch(diff: str, message: str, author: str | None, date: datetime | None = None) -> str:
    subject, _, body = message.partition("\n\n")
    d = (date or datetime.now(UTC)).strftime("%a, %d %b %Y %H:%M:%S +0000")
    return (
        "From 0000000000000000000000000000000000000000 Mon Sep 17 00:00:00 2001\n"
        f"From: {author or PLACEHOLDER}\nDate: {d}\nSubject: [PATCH] {subject}\n\n{body}\n---\n"
        f"{diffstat(diff)}\n\n{diff}--\nleakproof package\n"
    )


def evidence_rows(checks: dict[str, Any]) -> list[tuple[str, str, str]]:
    """(check, result, detail) for every check, the ones that did not run included."""
    rows = []
    for key, what in CHECKS:
        c = checks.get(key)
        if c is None:
            if key == "behavior":
                continue  # Juliet-only
            why = (
                "the adversary was off for this run (`--adversary`)"
                if key == "adversary"
                else "not part of this gate run"
            )
            rows.append((what, "not run", why))
            continue
        status, detail = c["status"], " ".join((c.get("detail") or "").split())[:180]
        result = {"pass": "pass", "fail": "FAIL", "skipped": "not run"}.get(status, status)
        rows.append((what, result, detail.replace("|", "/")))
    return rows


def submission(
    *,
    title: str,
    finding: dict[str, Any],
    root_cause: str,
    diff: str,
    checks: dict[str, Any],
    verdict: str,
    message: str,
    patch_name: str,
    source: str,
    issue_url: str | None = None,
) -> str:
    ev = strength(checks, None)
    tests_ran = (checks.get("tests") or {}).get("status") in ("pass", "fail")
    harness = (checks.get("refuzz") or {}).get("status") in (
        "pass",
        "fail",
    ) and "generated" not in ((checks.get("refuzz") or {}).get("detail") or "")
    banner = (
        "\n> **Verified, needs human review.** Neither project tests nor a fuzz harness ran, so the "
        "gate saw only the reproducer (and any generated or adversary inputs). Read the diff "
        "before sending.\n"
        if not tests_ran and not harness
        else ""
    )
    func, loc = _site(finding)
    rows = "\n".join(f"| {w} | {r} | {d} |" for w, r, d in evidence_rows(checks))
    return f"""# {title}: submission package (generated by `leakproof package`; nothing has been posted)
{banner}
{f"Issue: {issue_url}" + chr(10) if issue_url else ""}Defect: {finding.get("kind", "?")} in `{func or "?"}` (`{loc or "?"}`). Gate verdict: **{verdict}**; evidence: {ev["label"]}.

## The patch

`{patch_name}` (this directory), `git format-patch` form: apply with `git am {patch_name}`. The
author is `{PLACEHOLDER}` unless `--author` was given; fix it with
`git commit --amend --reset-author`.

```diff
{diff.rstrip()}
```

Why, as Leakproof's planner (a model) explained it before the fix was written. Check it against
the diff: the commit message body below is built from it.

> {" ".join(root_cause.split())[:900]}

## Evidence (from `{source}`)

| check | result | detail |
|---|---|---|
{rows}

## Commit message (in the patch)

```
{message}
```

## AI-assistance disclosure (put it in the PR or e-mail text)

> This fix was developed with Leakproof, an AI repair agent (Nemotron models on Nebius Token
> Factory); its candidate passed the sanitizer-based checks above. I reviewed the change and ran
> the project's tests myself before sending.

## Before sending

- [ ] Read the diff and the root cause; make sure you can explain the fix in your own words.
- [ ] Rewrite the commit message body if the planner's explanation is not what the diff fixes.
- [ ] Run the project's own tests in your build (the gate's results are above; yours count).
- [ ] Check the project's contribution guide and AI-contribution policy, and how it takes patches.
- [ ] Set your identity as the author (`git commit --amend --reset-author`).
- [ ] Keep the PR or e-mail short, in your own words, with the disclosure above.
"""


def package(
    *,
    out: Path,
    finding: dict[str, Any],
    root_cause: str,
    diff: str,
    checks: dict[str, Any],
    verdict: str,
    source: str,
    title: str,
    author: str | None = None,
    issue: str | None = None,
    issue_url: str | None = None,
) -> tuple[Path, Path]:
    diff = repo_diff(diff)
    message = commit_message(finding, root_cause, issue)
    slug = re.sub(r"[^a-z0-9]+", "-", message.split("\n")[0].lower()).strip("-")[:52]
    patch_name = f"0001-{slug}.patch"
    out.mkdir(parents=True, exist_ok=True)
    pp = out / patch_name
    pp.write_text(format_patch(diff, message, author), encoding="utf-8", newline="\n")
    sp = out / "SUBMISSION.md"
    sp.write_text(
        submission(
            title=title,
            finding=finding,
            root_cause=root_cause,
            diff=diff,
            checks=checks,
            verdict=verdict,
            message=message,
            patch_name=patch_name,
            source=source,
            issue_url=issue_url,
        ),
        encoding="utf-8",
        newline="\n",
    )
    return sp, pp


def _title(rec: dict[str, Any], fallback: str) -> str:
    p = rec.get("project")
    return (p.get("project") if isinstance(p, dict) else p) or fallback


def from_record(record: Path, candidate: str = "winner") -> dict[str, Any]:
    """Inputs for package() from a `leakproof fix` record."""
    rec = json.loads(record.read_text())
    if candidate == "winner":
        w = rec.get("winner") or {}
        key = (w.get("hypothesis_id"), w.get("worker_index"))
    else:
        hyp, idx = candidate.split(":")
        key = (hyp, int(idx))
    worker = next(
        x
        for x in rec["workers"]
        if (x["hypothesis_id"], x["worker_index"]) == key and x.get("gate")
    )
    return {
        "finding": rec["finding"],
        "root_cause": (rec.get("plan") or {}).get("root_cause") or "",
        "diff": worker["diff"],
        "checks": worker["gate"]["checks"],
        "verdict": worker["verdict"],
        "source": record.as_posix(),
        "title": _title(rec, rec["case"]),
    }


def from_gate_dir(gate_dir: Path, cid: str, record: Path | None = None) -> dict[str, Any]:
    """Inputs for package() from a gate run on stored candidates (scripts/gate_manual.py)."""
    gate = json.loads((gate_dir / "gate.json").read_text())
    cands = json.loads((gate_dir / "candidates.json").read_text())
    res = next(r for r in gate["results"] if r["hypothesis_id"] == cid)
    cand = next(c for c in cands["candidates"] if c["hypothesis_id"] == cid)
    rec = json.loads(record.read_text()) if record else {}
    return {
        "finding": cands.get("finding") or rec.get("finding") or {},
        "root_cause": (rec.get("plan") or {}).get("root_cause") or "",
        "diff": cand["diff"],
        "checks": res["checks"],
        "verdict": res["verdict"],
        "source": (gate_dir / "gate.json").as_posix(),
        "title": _title(rec, Path(gate.get("case", "case")).parent.name),
    }
