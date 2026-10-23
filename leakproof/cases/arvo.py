"""ARVO cases: real OSS-Fuzz crashes in `n132/arvo:<localId>-vul` images (docs/ARVO_NOTES.md).

prepare(): pull -> `arvo` (must trip) -> rebuild with our flags (-O0) -> `arvo` (must trip again)
-> commit that container as the baseline checkpoint. cleanup() removes the checkpoint and the
image (D-0027: one ARVO image on disk at a time).
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any

from leakproof.cases.base import BuildResult, Window
from leakproof.config import CACHE_DIR, REPO_ROOT
from leakproof.findings import parse_report, primary
from leakproof.runner import ImageRef, Runner

DB = CACHE_DIR / "arvo" / "arvo.db"
SHORTLIST = REPO_ROOT / "cases" / "arvo" / "shortlist_2026-10-22.json"
OUR_FLAGS = "-O0 -gline-tables-only -DFUZZING_BUILD_MODE_UNSAFE_FOR_PRODUCTION"
BUILD_ENV = {"CFLAGS": OUR_FLAGS, "CXXFLAGS": f"{OUR_FLAGS} -stdlib=libc++"}
WINDOW = 80
MAX_CRASH_FRAMES = 5
# Project test commands, run from the case workdir inside the rebuilt image (gate check 3).
# Filled per project after inspecting its image; None = no runnable suite found (stated).
TESTS: dict[str, str | None] = {}


@dataclass
class ArvoCase:
    id: str
    project: str
    image: str
    fuzz_target: str
    crash_type: str
    fix_commit: str
    meta: dict[str, Any]
    suite: str = "arvo"
    workdir: str = "/src"
    finding: dict[str, Any] = field(default_factory=dict)
    prep: dict[str, Any] = field(default_factory=dict)
    _baseline: ImageRef | None = None
    _sources: dict[str, str] = field(default_factory=dict)

    @classmethod
    def load(cls, local_id: str | int) -> ArvoCase:
        con = sqlite3.connect(DB)
        con.row_factory = sqlite3.Row
        row = con.execute("select * from arvo where localId = ?", (int(local_id),)).fetchone()
        if row is None:
            raise KeyError(f"{local_id} not in {DB}")
        sl = json.loads(SHORTLIST.read_text())
        entry = next(
            (
                r
                for tier in ("tier1", "tier2", "reserves")
                for r in sl.get(tier, [])
                if str(r.get("localId")) == str(local_id)
            ),
            {},
        )
        return cls(
            id=str(local_id),
            project=row["project"],
            image=f"n132/arvo:{local_id}-vul",
            fuzz_target=row["fuzz_target"],
            crash_type=row["crash_type"],
            fix_commit=row["fix_commit"],
            meta={
                "tier": entry.get("tier"),
                "tests_note": entry.get("tests"),
                "patch_url": row["patch_url"],
                "repo": row["repo_addr"],
            },
        )

    @property
    def tests_cmd(self) -> str | None:
        return TESTS.get(self.project)

    @property
    def src_root(self) -> str:
        return f"/src/{self.project}/"

    # ---------------------------------------------------------------- baseline
    def prepare(self, runner: Runner) -> ImageRef:
        t0 = time.monotonic()
        subprocess.run(["docker", "pull", "-q", self.image], check=True, capture_output=True)
        self.prep["pull_s"] = round(time.monotonic() - t0, 1)
        self.workdir = (
            subprocess.run(
                ["docker", "image", "inspect", "-f", "{{.Config.WorkingDir}}", self.image],
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
            or "/src"
        )
        ref = ImageRef("docker", self.image)
        shipped = runner.run(ref, "arvo", cwd=self.workdir, timeout_s=300, network=False)
        f0 = primary(parse_report(shipped.stderr + shipped.stdout))
        self.prep.update(shipped_exit=shipped.exit_code, shipped_kind=f0.kind if f0 else None)
        if f0 is None:
            raise RuntimeError(
                f"{self.id}: shipped harness did not trip (exit {shipped.exit_code})"
            )
        rebuilt = runner.run(
            ref,
            "arvo compile > /tmp/compile.log 2>&1; rc=$?; tail -20 /tmp/compile.log; "
            "[ $rc = 0 ] || exit 97; arvo",
            env=BUILD_ENV,
            cwd=self.workdir,
            timeout_s=1800,
            network=False,
            save=True,
        )
        self.prep.update(rebuild_s=rebuilt.elapsed_s, rebuild_peak_kb=rebuilt.max_rss_kb)
        if rebuilt.exit_code == 97:
            raise RuntimeError(
                f"{self.id}: rebuild with our flags failed:\n{rebuilt.stdout[-1500:]}"
            )
        f1 = primary(parse_report(rebuilt.stderr + rebuilt.stdout))
        self.prep["rebuilt_kind"] = f1.kind if f1 else None
        if f1 is None or rebuilt.image is None:
            raise RuntimeError(f"{self.id}: -O0 rebuild no longer trips (exit {rebuilt.exit_code})")
        self.finding = f1.to_dict(include_raw=False)
        self.prep["report_tail"] = (rebuilt.stderr + rebuilt.stdout)[-6000:]
        self._baseline = rebuilt.image
        return rebuilt.image

    def cleanup(self, runner: Runner) -> None:
        for ref in (self._baseline, ImageRef("docker", self.image)):
            if ref is not None and hasattr(runner, "remove_image"):
                runner.remove_image(ref)
        self._baseline = None

    # ---------------------------------------------------------------- worker-visible view
    def _frames(self) -> list[tuple[str, dict[str, Any]]]:
        f = self.finding
        user = [
            fr for fr in f.get("frames", []) if (fr.get("file") or "").startswith(self.src_root)
        ]
        out = [("crash", fr) for fr in user[:MAX_CRASH_FRAMES]]
        for label, key in (("alloc", "alloc_stack"), ("free", "free_stack")):
            stack = [
                fr for fr in f.get(key, []) if (fr.get("file") or "").startswith(self.src_root)
            ]
            out += [(label, fr) for fr in stack[:2]]
        return [(lbl, fr) for lbl, fr in out if fr.get("line")]

    def visible_sources(self, runner: Runner) -> dict[str, str]:
        if not self._sources:
            assert self._baseline is not None, "prepare() first"
            for path in dict.fromkeys(fr["file"] for _, fr in self._frames()):
                try:
                    self._sources[path] = runner.read(self._baseline, path).decode(errors="replace")
                except (RuntimeError, IsADirectoryError):
                    continue
        return self._sources

    def windows(self, runner: Runner) -> list[Window]:
        sources = self.visible_sources(runner)
        spans: dict[str, list[list[int]]] = {}
        marks: dict[str, dict[int, str]] = {}
        for label, fr in self._frames():
            path, line = fr["file"], fr["line"]
            if path not in sources:
                continue
            marks.setdefault(path, {}).setdefault(line, f"{label}: {fr['function']}")
            spans.setdefault(path, []).append([max(1, line - WINDOW), line + WINDOW])
        out = []
        for path, ranges in spans.items():
            lines = sources[path].splitlines()
            merged: list[list[int]] = []
            for lo, hi in sorted(ranges):
                if merged and lo <= merged[-1][1] + 1:
                    merged[-1][1] = max(merged[-1][1], hi)
                else:
                    merged.append([lo, hi])
            for lo, hi in merged:
                hi = min(hi, len(lines))
                out.append(
                    Window(
                        path,
                        lo,
                        hi,
                        "\n".join(lines[lo - 1 : hi]),
                        {k: v for k, v in marks[path].items() if lo <= k <= hi},
                    )
                )
        return out

    def restore(self, path: str, visible: str) -> str:
        return visible

    def build_description(self) -> str:
        tests = self.tests_cmd or "none runnable in the image; the gate states this"
        return (
            f"Open-source project `{self.project}` ({self.meta.get('repo')}), built by OSS-Fuzz's "
            f"build.sh with clang + AddressSanitizer into the libFuzzer harness "
            f"`{self.fuzz_target}`; the crash comes from a fuzzer-found input. Source tree under "
            f"{self.src_root}. Project tests: {tests}."
        )

    def build_candidate(
        self, runner: Runner, baseline: ImageRef, files: dict[str, str]
    ) -> BuildResult:
        t0 = time.monotonic()
        res = runner.run(
            baseline,
            "arvo compile > /tmp/compile.log 2>&1; rc=$?; grep -E 'error|Error' /tmp/compile.log "
            "| head -30; tail -15 /tmp/compile.log; exit $rc",
            files={k: v.encode() for k, v in files.items()},
            env=BUILD_ENV,
            cwd=self.workdir,
            timeout_s=1800,
            network=False,
        )
        return BuildResult(res.exit_code == 0, res.stdout[-3000:], round(time.monotonic() - t0, 2))

    def record(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project": self.project,
            "image": self.image,
            "workdir": self.workdir,
            "fuzz_target": self.fuzz_target,
            "crash_type": self.crash_type,
            "fix_commit": self.fix_commit,
            "tests_cmd": self.tests_cmd,
            **self.meta,
            "prep": self.prep,
        }
