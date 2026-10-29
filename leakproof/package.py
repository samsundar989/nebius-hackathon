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


def repo_diff(diff: str, subdir: str = "") -> str:
    """Container paths (a/src/<project>/x) -> repository paths (a/x), with `diff --git` headers.
    `subdir`: where the upstream repository sits inside the case tree (a config with src = "."
    and the clone in src/), stripped as well so the patch applies upstream."""
    out = []
    prefix = r"src/[^/]+/" + (re.escape(subdir.strip("/")) + "/" if subdir else "")
    for line in diff.splitlines():
        line = re.sub(rf"^(--- a|\+\+\+ b)/{prefix}", r"\1/", line)
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
    # git diff --stat's own layout: names padded to one column, counts right-aligned, and a
    # summary that pluralises and leaves out zero insertions or deletions.
    width = max((len(f) for f in files), default=0)
    count = max((len(str(a + d)) for a, d in files.values()), default=1)
    rows = [f" {f:<{width}} | {a + d:>{count}} {'+' * a}{'-' * d}" for f, (a, d) in files.items()]
    ins, dels = sum(v[0] for v in files.values()), sum(v[1] for v in files.values())
    n = len(files)
    summary = f" {n} file{'s' if n != 1 else ''} changed"
    if ins:
        summary += f", {ins} insertion{'s' if ins != 1 else ''}(+)"
    if dels:
        summary += f", {dels} deletion{'s' if dels != 1 else ''}(-)"
    rows.append(summary)
    return "\n".join(rows)


def _site(finding: dict[str, Any]) -> tuple[str, str]:
    """(function, repo-relative file:line) of the defect."""
    func = ""
    for fr in finding.get("frames") or []:
        f = fr.get("file") or ""
        if f.startswith("/src/") and not f.startswith("/src/llvm-project/"):
            # C++ frames carry the full signature: keep `Class::name` for a readable subject.
            func = (fr.get("function") or "").split("(")[0]
            break
    loc = re.sub(r"^/src/[^/]+/", "", finding.get("location") or "")
    return func, loc


def _changed(diff: str) -> tuple[list[str], dict[str, list[int]]]:
    """(the +/- lines, {file: [added, removed]}) of a unified diff."""
    lines, files, cur = [], {}, None
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            cur = line[6:].split("\t")[0]
            files[cur] = [0, 0]
        elif cur and line[:1] in "+-" and not line.startswith(("+++", "---")):
            lines.append(line)
            files[cur][0 if line[0] == "+" else 1] += 1
    return lines, files


def commit_message(
    finding: dict[str, Any], diff: str, issue: str | None, partial: bool = False
) -> str:
    """Describes the diff, never the plan (review #12): the subject names the defect and the
    function from the sanitizer report; the body says what the report showed and quotes the
    changed lines when the change is small (at most 6), else summarises them per file."""
    func, loc = _site(finding)
    kind = finding.get("kind") or "memory error"
    stem = Path(loc.split(":")[0]).stem or "fix"
    where = f"{func}()" if func else Path(loc.split(":")[0]).name or "the reported code"
    subject = f"{stem}: fix {kind} in {where}"
    lines, files = _changed(repo_diff(diff))
    report = f"AddressSanitizer reports a {kind} in {where}" + (f" ({loc})." if loc else ".")
    body = textwrap.wrap(report, 72)
    if 0 < len(lines) <= 6:
        body += ["", f"The change, in {', '.join(files)}:", ""]
        body += [f"    {ln}" for ln in lines]
    elif lines:
        parts = [f"{f} (+{a}/-{d})" for f, (a, d) in files.items()]
        body += textwrap.wrap("This changes " + ", ".join(parts) + ".", 72)
    msg = subject + "\n\n" + "\n".join(body)
    if issue:
        msg += f"\n\n{'Part of' if partial else 'Fixes'} #{issue.lstrip('#')}."
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


def tested_lines(checks: dict[str, Any]) -> list[str]:
    """How the change was tested, in a maintainer's words, from the gate's checks."""
    out = []
    if (checks.get("patched") or {}).get("status") == "pass":
        out.append("the reproducer from the issue runs clean under AddressSanitizer/UBSan")
    tests = checks.get("tests") or {}
    if tests.get("status") == "pass":
        out.append("the project's own tests pass")
    elif tests.get("status") == "skipped":
        out.append(f"the project's own tests could not be used ({tests.get('detail', '')[:80]})")
    adv = checks.get("adversary") or {}
    if adv.get("status") == "pass":
        out.append("inputs written to break the patch found nothing (" + adv["detail"][:60] + ")")
    refuzz = checks.get("refuzz") or {}
    if refuzz.get("status") == "pass":
        out.append("variants of the crash input found no new crash")
    return out


def pr_body(message: str, checks: dict[str, Any], not_fixed: str = "") -> str:
    """A ready pull-request description: what changed, what is not fixed, how it was tested,
    and the AI-assistance disclosure. The sender reads and edits it before use."""
    subject, _, body = message.partition("\n\n")
    ref = body.rsplit("\n\n", 1)[-1] if ("Fixes #" in body or "Part of #" in body) else ""
    change = body[: len(body) - len(ref)].strip() if ref else body.strip()
    parts = [change]
    if not_fixed:
        parts.append(f"Not fixed here: {not_fixed}")
    parts.append("Tested: " + "; ".join(tested_lines(checks)) + ".")
    parts.append(
        "This patch was developed with Leakproof, an AI repair agent; its candidate passed "
        "sanitizer-based checks. I reviewed the change and ran the project's tests myself."
    )
    if ref:
        parts.append(ref)
    return "\n\n".join(parts) + "\n"


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
    not_fixed: str = "",
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
    m = re.match(r"https://github\.com/([^/]+)/([^/]+)/issues/(\d+)", issue_url or "")
    owner, repo, num = m.groups() if m else ("OWNER", "REPO", "N")
    subject = message.split("\n")[0]
    partial_note = f"\n**Partial fix.** Not fixed here: {not_fixed}\n" if not_fixed else ""
    return f"""# {title}: submission package (generated by `leakproof package`; nothing has been posted)
{banner}
{f"Issue: {issue_url}" + chr(10) if issue_url else ""}Defect: {finding.get("kind", "?")} in `{func or "?"}` (`{loc or "?"}`). Gate verdict: **{verdict}**; evidence: {ev["label"]}.
{partial_note}
## The patch

`{patch_name}` (this directory), `git format-patch` form: apply with `git am {patch_name}`. The
author is `{PLACEHOLDER}` unless `--author` was given; fix it with
`git commit --amend --reset-author`.

```diff
{diff.rstrip()}
```

## Planner's analysis (written before the fix; check it against the diff)

Nemotron 3 Ultra wrote this root-cause analysis before any patch existed. It can describe a
different mechanism than the one the final diff fixes, so it is here for the reviewer and never
in the commit message.

> {" ".join(root_cause.split())[:900] or "(no planner analysis in this run)"}

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
- [ ] Add a sentence on *why* the change fixes the bug to the commit message, in your words.
- [ ] Run the project's own tests in your build (the gate's results are above; yours count).
- [ ] Check the project's contribution guide and AI-contribution policy, and how it takes patches.
- [ ] Set your identity as the author (`git commit --amend --reset-author`).
- [ ] Keep the PR or e-mail short, in your own words, with the disclosure above.

## Send it in 5 minutes (only after the checklist; nothing here has been run)

The PR description is ready in `PR_BODY.md` (this directory): what changed, what is not fixed,
how it was tested, and the disclosure. Read it and change anything you would not say yourself.
First check the project's README or CONTRIBUTING for how it takes patches; some prefer a mailing
list, in which case send the patch file with `git send-email` instead.

**GitHub, in the browser**
1. Open https://github.com/{owner}/{repo} and click **Fork**.
2. In your fork, open the file the diff above changes, click the pencil (Edit), make the same
   change, and commit it to a new branch (for example `leakproof-fix-{num}`).
3. Click **Compare & pull request**; title: `{subject}`; paste `PR_BODY.md` as the description.

**Command line** (needs `gh`, logged in)
```
gh repo fork {owner}/{repo} --clone && cd {repo}
git checkout -b leakproof-fix-{num}
git am /path/to/{patch_name}
git commit --amend --reset-author --no-edit
git push -u origin leakproof-fix-{num}
gh pr create --repo {owner}/{repo} --title "{subject}" --body-file /path/to/PR_BODY.md
```

If the maintainer prefers to fix it differently, thank them and close the PR.
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
    repo_subdir: str = "",
    partial: bool = False,
    not_fixed: str = "",
) -> tuple[Path, Path]:
    diff = repo_diff(diff, repo_subdir)
    if repo_subdir:
        loc = re.sub(
            rf"^(/src/[^/]+/){re.escape(repo_subdir.strip('/'))}/",
            r"\1",
            finding.get("location") or "",
        )
        finding = finding | {"location": loc}
    message = commit_message(finding, diff, issue, partial)
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
            not_fixed=not_fixed,
        ),
        encoding="utf-8",
        newline="\n",
    )
    (out / "PR_BODY.md").write_text(
        pr_body(message, checks, not_fixed), encoding="utf-8", newline="\n"
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
