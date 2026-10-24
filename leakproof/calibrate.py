"""Developer fixes as gate candidates (P1 calibration). Gate side only.

The developer's fix is the answer key: nothing on the worker path (planner, worker, branch,
context, edits, fix) may import this module (tests/test_isolation.py).

dev_fix_candidate(): fetch the fix commit's patch from the upstream repo (preparation step, on
the host, network on), apply it to the baseline tree in a container with `git apply --reject`,
and emit the editable files it touched as an ordinary gate candidate. The `-fix` image is not
used: it sits at a later revision, so its tree differs from the baseline in unrelated files
(jq 42530604: 10 source files). build_reference(): the same files built on the baseline, saved
as an image the gate uses to attribute refuzz crashes.
"""

from __future__ import annotations

import base64
import difflib
import re
import shlex
import sqlite3
import urllib.request
from typing import Any

from leakproof.cases.arvo import BUILD_ENV, COMPILE_CMD, DB, ArvoCase, rebuild_prep_cmd
from leakproof.config import CACHE_DIR
from leakproof.gate import HARNESS_ENTRY, MARK, SOURCE_EXT, split
from leakproof.runner import ImageRef, LocalDockerRunner

PATCH_CACHE = CACHE_DIR / "arvo" / "dev_patches"
COMMIT_URL = re.compile(r"https://github\.com/([^/]+/[^/]+)/commit/([0-9a-f]{7,40})")
MAX_FILES = 40  # more than this is a refactor, not a fix; recorded, not gated
_PLUS = re.compile(r"^\+\+\+ b/(\S+)", re.M)


def fix_commits(case_id: str) -> tuple[str | None, list[list[str]]]:
    """(github owner/repo, commit sets to try in order): ARVO's located patch, then every
    commit ARVO lists as the fix range (oldest first)."""
    con = sqlite3.connect(DB)
    row = con.execute(
        "select patch_url, fix_commit, repo_addr from arvo where localId = ?", (int(case_id),)
    ).fetchone()
    patch_url, fix_commit, repo_addr = row
    m = COMMIT_URL.match(patch_url or "")
    rm = re.match(r"https://github\.com/([^/]+/[^/.]+)", repo_addr or "")
    repo = m.group(1) if m else (rm.group(1) if rm else None)
    sets = [[m.group(2)]] if m else []
    listed = [c for c in (fix_commit or "").split() if c]
    if listed and listed not in sets:
        sets.append(listed)
    return repo, sets


def fetch_patch(repo: str, sha: str) -> str:
    path = PATCH_CACHE / f"{repo.replace('/', '__')}__{sha}.patch"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(
            f"https://github.com/{repo}/commit/{sha}.patch", headers={"User-Agent": "leakproof"}
        )
        with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310 - fixed https host
            path.write_bytes(resp.read())
    return path.read_text(encoding="utf-8", errors="replace")


def _apply_script(project: str, n: int, editable: list[str]) -> str:
    lines = [f"cd /src/{shlex.quote(project)}"]
    for i in range(n):
        # Whole patch when it applies cleanly; otherwise the hunks that do (--reject leaves
        # <file>.rej for the rest, which marks the candidate partial).
        p = f"/tmp/dev/{i}.patch"
        lines.append(
            f"if git apply --check --whitespace=nowarn {p} > /tmp/dev/{i}.log 2>&1; "
            f"then git apply --whitespace=nowarn {p}; echo clean >> /tmp/dev/{i}.log; "
            f"else git apply --reject --whitespace=nowarn {p} >> /tmp/dev/{i}.log 2>&1; fi; "
            f"printf '\\n{MARK} apply_{i}\\n'; tail -c 3000 /tmp/dev/{i}.log"
        )
    for j, rel in enumerate(editable):
        q = shlex.quote(rel)
        lines.append(
            f"printf '\\n{MARK} file_{j}\\n'; [ -f {q} ] && base64 -w0 {q}; "
            f"printf '\\n{MARK} rej_{j}\\n'; [ -f {q}.rej ] && echo rejected"
        )
    return "\n".join(lines)


def dev_fix_candidate(
    case: ArvoCase, runner: LocalDockerRunner, baseline: ImageRef
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """(candidate or None, metadata). meta['partial'] = some editable hunk did not apply."""
    repo, sets = fix_commits(case.id)
    meta: dict[str, Any] = {"repo": repo, "commit_sets": sets}
    if not repo or not sets:
        meta["error"] = "no GitHub fix commit recorded"
        return None, meta
    patches: list[str] = []
    editable: list[str] = []
    for commits in sets:
        try:
            patches = [fetch_patch(repo, c) for c in commits]
        except OSError as exc:
            meta.setdefault("fetch_errors", []).append(f"{commits[0][:10]}: {exc}")
            continue
        touched = list(dict.fromkeys(p for text in patches for p in _PLUS.findall(text)))
        # The gate's own rule (diff_scope): project sources with a source extension, outside
        # tests/fuzz/harness directories. Docs and changelogs in a fix commit are dropped.
        editable = [
            p for p in touched if case._editable(f"{case.src_root}{p}") and p.endswith(SOURCE_EXT)
        ]
        meta.update(
            commits=commits,
            touched=touched[:200],
            excluded=[p for p in touched if p not in editable][:200],
        )
        if editable:
            break
    if not editable:
        meta["error"] = "no fix commit touches an editable source file (or none could be fetched)"
        return None, meta
    if len(editable) > MAX_FILES:
        meta["error"] = f"{len(editable)} editable files touched (> {MAX_FILES})"
        return None, meta
    res = runner.run(
        baseline,
        _apply_script(case.project, len(patches), editable),
        files={f"/tmp/dev/{i}.patch": p.encode() for i, p in enumerate(patches)},
        cwd="/",
        timeout_s=300,
        network=False,
    )
    sec = split(res.stdout)
    meta["apply_log"] = {k: v[-600:] for k, v in sec.items() if k.startswith("apply_")}
    files: dict[str, str] = {}
    diff: list[str] = []
    rejected = []
    for j, rel in enumerate(editable):
        path = f"{case.src_root}{rel}"
        if sec.get(f"rej_{j}", "").strip():
            rejected.append(rel)
        raw = sec.get(f"file_{j}", "").strip()
        if not raw:
            continue  # deleted by the fix: not expressible as a file map; recorded below
        new = base64.b64decode(raw).decode(errors="replace")
        if HARNESS_ENTRY in new:
            meta.setdefault("harness_files", []).append(rel)
            continue
        try:
            old = runner.read(baseline, path).decode(errors="replace")
        except (RuntimeError, IsADirectoryError):
            old = ""
        if new == old:
            continue
        files[path] = new
        diff += difflib.unified_diff(
            old.splitlines(keepends=True), new.splitlines(keepends=True), f"a{path}", f"b{path}"
        )
    meta["files"] = sorted(files)
    meta["rejected_hunks_in"] = rejected
    meta["partial"] = bool(rejected) or len(files) < len(editable)
    if not files:
        meta["error"] = (
            "out_of_scope: the fix is in the fuzz harness"
            if meta.get("harness_files")
            else "fix commit did not apply to the baseline"
        )
        return None, meta
    cand = {
        "hypothesis_id": "DEV",
        "worker_index": 0,
        # Same rules as a model candidate with no declared strategy: calibration measures
        # the gate as it judges models, so the developer gets no exemptions.
        "strategy": "other",
        "files": files,
        "diff": "".join(diff),
    }
    return cand, meta


def build_reference(
    case: ArvoCase, runner: LocalDockerRunner, baseline: ImageRef, files: dict[str, str]
) -> tuple[ImageRef | None, str]:
    res = runner.run(
        baseline,
        rebuild_prep_cmd(case.project, case.fuzz_target, files)
        + f"{COMPILE_CMD} > /tmp/compile.log 2>&1; rc=$?; tail -20 /tmp/compile.log; exit $rc",
        files={k: v.encode() for k, v in files.items()},
        env=BUILD_ENV,
        cwd=case.workdir,
        timeout_s=1800,
        network=False,
        save=True,
    )
    if res.exit_code != 0:
        if res.image is not None:
            runner.remove_image(res.image)
        return None, res.stdout[-1500:]
    return res.image, ""
