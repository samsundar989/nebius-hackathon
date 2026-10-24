"""Developer fixes as gate candidates (P1 calibration). Gate side only.

The developer's fix is the answer key: nothing on the worker path (planner, worker, branch,
context, edits, fix) may import this module (tests/test_isolation.py).

dev_fix_candidate(): compare the project's source files in `n132/arvo:<id>-fix` against our
baseline (git-tracked files when the tree has .git, else every source file), keep the ones a
candidate may edit, and emit them as an ordinary gate candidate. build_reference(): the same
files built on the baseline, saved as an image the gate uses to attribute refuzz crashes.
"""

from __future__ import annotations

import difflib
import subprocess
import time
from typing import Any

from leakproof.cases.arvo import BUILD_ENV, ArvoCase, rebuild_prep_cmd
from leakproof.gate import SOURCE_EXT
from leakproof.runner import ImageRef, LocalDockerRunner

MAX_FILES = 40  # more than this is generated code or a refactor, not a fix; recorded, not gated


def _list_cmd(project: str) -> str:
    ext = "|".join(e.lstrip(".") for e in SOURCE_EXT)
    return (
        f"cd /src/{project} && if git rev-parse --git-dir >/dev/null 2>&1; then echo '#git'; "
        "git ls-files; else echo '#find'; find . -type f; fi | sed 's#^\\./##' "
        f"| grep -E '^#|\\.({ext})$' | while read -r f; do case $f in '#'*) echo \"$f\";; "
        '*) [ -f "$f" ] && md5sum "$f";; esac; done'
    )


def sources(runner: LocalDockerRunner, image: ImageRef, project: str) -> tuple[str, dict[str, str]]:
    res = runner.run(image, _list_cmd(project), cwd="/", timeout_s=600, network=False)
    method, out = "none", {}
    for line in res.stdout.splitlines():
        if line.startswith("#"):
            method = line[1:]
            continue
        md5, _, path = line.partition("  ")
        if path:
            out[f"/src/{project}/{path}"] = md5
    return method, out


def dev_fix_candidate(
    case: ArvoCase, runner: LocalDockerRunner, baseline: ImageRef
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """(candidate or None, metadata). The fix image is pulled here and removed by the caller."""
    fix = ImageRef("docker", case.image.replace("-vul", "-fix"))
    meta: dict[str, Any] = {"fix_image": fix.ref}
    t0 = time.monotonic()
    pulled = subprocess.run(["docker", "pull", "-q", fix.ref], capture_output=True, text=True)
    meta["pull_s"] = round(time.monotonic() - t0, 1)
    if pulled.returncode != 0:
        meta["error"] = f"pull failed: {pulled.stderr.strip()[-300:]}"
        return None, meta
    m_fix, fix_src = sources(runner, fix, case.project)
    m_base, base_src = sources(runner, baseline, case.project)
    meta["method"] = {"fix": m_fix, "baseline": m_base}
    changed = sorted(p for p, h in fix_src.items() if base_src.get(p) != h)
    meta["removed"] = sorted(set(base_src) - set(fix_src))
    editable = [p for p in changed if case._editable(p)]
    meta["changed"] = changed[:200]
    meta["excluded"] = [p for p in changed if p not in editable][:200]
    if not editable:
        meta["error"] = "no editable source file differs between -fix and the baseline"
        return None, meta
    if len(editable) > MAX_FILES:
        meta["error"] = (
            f"{len(editable)} editable files differ (> {MAX_FILES}): not a fix-sized diff"
        )
        return None, meta
    files: dict[str, str] = {}
    diff: list[str] = []
    for path in editable:
        new = runner.read(fix, path).decode(errors="replace")
        old = runner.read(baseline, path).decode(errors="replace") if path in base_src else ""
        files[path] = new
        diff += difflib.unified_diff(
            old.splitlines(keepends=True),
            new.splitlines(keepends=True),
            f"a{path}",
            f"b{path}",
            n=3,
        )
    meta["files"] = editable
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
        + "arvo compile > /tmp/compile.log 2>&1; rc=$?; tail -20 /tmp/compile.log; exit $rc",
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
