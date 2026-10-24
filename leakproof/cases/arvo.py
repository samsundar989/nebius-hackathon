"""ARVO cases: real OSS-Fuzz crashes in `n132/arvo:<localId>-vul` images (docs/ARVO_NOTES.md).

prepare(): pull -> `arvo` (must trip) -> rebuild with our flags (-O0) -> `arvo` (must trip again)
-> commit that container as the baseline checkpoint. cleanup() removes the checkpoint and the
image (D-0027: one ARVO image on disk at a time).
"""

from __future__ import annotations

import json
import posixpath
import re
import shlex
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
# libFuzzer for every case (D-0046/D-0047): the gate's refuzz drives the harness with libFuzzer
# flags, which an AFL++/honggfuzz build ignores (libplist 42519914 "fuzzed" 0 executions).
# `arvo compile` cannot be told: /bin/arvo hard-codes `export FUZZING_ENGINE=afl|honggfuzz`
# before calling OSS-Fuzz's `compile`, so we call `compile` ourselves with ARVO's language.
COMPILE_CMD = (
    "( eval \"$(grep -E '^export FUZZING_LANGUAGE=' /bin/arvo)\"; "
    "export FUZZING_ENGINE=libfuzzer SANITIZER=address ARCHITECTURE=x86_64; compile )"
)
WINDOW = 80


def rebuild_prep_cmd(
    project: str, fuzz_target: str, files: dict[str, str], clean: bool = False
) -> str:
    """Shell prefix that makes `arvo compile` really rebuild what we changed (D-0041/D-0042).

    - touch copied-in sources with the container's clock (their mtime is the Windows host's);
    - delete the harness binary: some fuzzer Makefile rules depend only on the harness .cpp, not
      on the project library (mosquitto), so an existing binary is never relinked;
    - clean=True (baseline): delete objects/archives too, since make does not rebuild when only
      CFLAGS change and the image's objects are -O1.
    """
    cmd = f"touch {shlex.join(sorted(files))}; " if files else ""
    target = shlex.quote(fuzz_target)
    cmd += f"rm -f /out/{target}; find /src/{project} -type f -name {target} -delete; "
    if clean:
        cmd += (
            f"find /src/{project} -type f \\( -name '*.o' -o -name '*.lo' -o -name '*.a' "
            "-o -name '*.la' \\) -delete; "
        )
    return cmd


# OSS-Fuzz build scripts are written to run once (`mkdir build`, `mkdir /src/seeds`), and the
# baseline has already run them, so every later rebuild would die there (D-0047: md4c, miniz,
# libzip, h3, jq 42531297). Installed into the baseline: a mkdir whose already-existing
# directory arguments are no error; everything else goes to the real /bin/mkdir unchanged.
MKDIR_SHIM = r"""mkdir -p /usr/local/bin && cat > /usr/local/bin/mkdir <<'LPEOF'
#!/bin/bash
args=()
for a in "$@"; do
  if [[ $a != -* && -d $a ]]; then continue; fi
  args+=("$a")
done
for a in "${args[@]}"; do [[ $a == -* ]] || exec /bin/mkdir "${args[@]}"; done
exit 0
LPEOF
chmod +x /usr/local/bin/mkdir
"""
HARNESS_DIRS = re.compile(r"/(tests?|fuzz|fuzzing|fuzzers?|oss-?fuzz|harness(es)?)/", re.I)
MAX_CRASH_FRAMES = 5
# Project test commands, run from the case workdir inside the rebuilt image (gate check 3).
# Filled per project after inspecting its image; None = no runnable suite found (stated).
TESTS: dict[str, str | None] = {
    # 7 of jq's 8 suites; tests/shtest already fails on the unpatched -O0 image (runs/arvo_inspect).
    "jq": 'ASAN_OPTIONS=detect_leaks=0 make check-TESTS TESTS="tests/utf8test tests/base64test '
    'tests/optionaltest tests/onigtest tests/manonigtest tests/mantest tests/jqtest"',
    # test/unit needs CUnit, which the image lacks (and the gate runs offline).
    "mosquitto": None,
}


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

    # ---------------------------------------------------------------- gate hooks (gate side)
    # The gate drives every suite with a harness the same way; these say how for ARVO.
    build_env = BUILD_ENV
    reproduce_cmd = "arvo"

    @property
    def harness_path(self) -> str | None:
        return f"/out/{self.fuzz_target}"

    @property
    def artifact_path(self) -> str | None:
        return self.harness_path

    def gate_build_cmd(self, files: dict[str, str]) -> str:
        return rebuild_prep_cmd(self.project, self.fuzz_target, files) + COMPILE_CMD

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
            MKDIR_SHIM
            + rebuild_prep_cmd(self.project, self.fuzz_target, {}, clean=True)
            + f"{COMPILE_CMD} > /tmp/compile.log 2>&1; rc=$?; tail -20 /tmp/compile.log; "
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
    def _editable(self, path: str | None) -> bool:
        """Project sources, minus the fuzz harness and tests (the gate rejects edits there)."""
        return bool(path) and path.startswith(self.src_root) and not HARNESS_DIRS.search(path)

    def _frames(self) -> list[tuple[str, dict[str, Any]]]:
        """Crash/alloc/free frames in editable sources, paths normalized (`src/../lib/x.c`)."""
        f = {
            k: [
                {**fr, "file": posixpath.normpath(fr["file"]) if fr.get("file") else None}
                for fr in self.finding.get(k) or []
            ]
            for k in ("frames", "alloc_stack", "free_stack")
        }
        user = [fr for fr in f.get("frames", []) if self._editable(fr.get("file"))]
        out = [("crash", fr) for fr in user[:MAX_CRASH_FRAMES]]
        for label, key in (("alloc", "alloc_stack"), ("free", "free_stack")):
            stack = [fr for fr in f.get(key, []) if self._editable(fr.get("file"))]
            out += [(label, fr) for fr in stack[:2]]
        return [(lbl, fr) for lbl, fr in out if fr.get("line")]

    def visible_sources(self, runner: Runner) -> dict[str, str]:
        if not self._sources:
            assert self._baseline is not None, "prepare() first"
            for path in dict.fromkeys(fr["file"] for _, fr in self._frames()):
                try:
                    text = runner.read(self._baseline, path).decode(errors="replace")
                except (RuntimeError, IsADirectoryError):
                    continue
                # Harnesses outside a fuzz/ directory (pcre2's src/pcre2_fuzzsupport.c).
                if "LLVMFuzzerTestOneInput" not in text:
                    self._sources[path] = text
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
            rebuild_prep_cmd(self.project, self.fuzz_target, files)
            + f"{COMPILE_CMD} > /tmp/compile.log 2>&1; rc=$?; grep -E 'error|Error' /tmp/compile.log "
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
