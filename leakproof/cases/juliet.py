"""Juliet 1.3 cases (cases/juliet/<id>.json, written by scripts/juliet_run.py).

Workers see the bad path only: the `#ifndef OMITGOOD` block (it contains the reference fixes)
and the `#ifdef INCLUDEMAIN` block (deleting the call to bad() would "fix" anything) are replaced
by marker comments, which `restore` swaps back after editing.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from leakproof.cases.base import BuildResult, Window
from leakproof.config import CACHE_DIR, REPO_ROOT
from leakproof.runner import ImageRef, Runner

JULIET = CACHE_DIR / "juliet" / "C"
CASES_DIR = REPO_ROOT / "cases" / "juliet"
SUPPORT = ["io.c", "std_testcase.h", "std_testcase_io.h", "std_thread.h"]
IMAGE = ImageRef("docker", "leakproof/cpp-sanitizers:e0")
# The same toolchain on Nebius Sandboxes, built once by scripts/sandboxes_setup.py (D-0053).
IMAGES = {"docker": IMAGE, "sandboxes": ImageRef("sandboxes", "tag:lp-cpp-sanitizers")}
HIDDEN = {
    "good": (
        re.compile(r"^#ifndef OMITGOOD\b.*?^#endif /\* OMITGOOD \*/[^\n]*\n?", re.M | re.S),
        "/* [LEAKPROOF: good-path code omitted; do not add or remove this line] */\n",
    ),
    "main": (
        re.compile(r"^#ifdef INCLUDEMAIN\b.*?^#endif[^\n]*\n?", re.M | re.S),
        "/* [LEAKPROOF: test driver main() omitted; do not add or remove this line] */\n",
    ),
}


def load_case_json(case_id: str) -> dict[str, Any]:
    return json.loads((CASES_DIR / f"{case_id}.json").read_text())


@dataclass
class JulietCase:
    id: str
    data: dict[str, Any]
    suite: str = "juliet"
    _hidden: dict[str, dict[str, str]] = field(default_factory=dict)
    _baseline: ImageRef | None = None

    @classmethod
    def load(cls, case_id: str) -> JulietCase:
        return cls(case_id, load_case_json(case_id))

    @property
    def project(self) -> str:
        return f"juliet/{self.data['cwe']}"

    @property
    def finding(self) -> dict[str, Any]:
        return self.data["finding"]

    @property
    def reproducible(self) -> bool:
        return bool(self.data.get("reproducible"))

    def source_files(self) -> list[str]:
        return [f for f in self.data["files"] if f.endswith((".c", ".cpp"))]

    def original(self, name: str) -> str:
        return (JULIET / self.data["dir"] / name).read_text()

    # ---------------------------------------------------------------- worker-visible view
    def visible_sources(self, runner: Runner | None = None) -> dict[str, str]:
        out = {}
        for name in self.source_files():
            text = self.original(name)
            hidden = {}
            for _key, (pattern, marker) in HIDDEN.items():
                m = pattern.search(text)
                if m:
                    hidden[marker] = m.group(0)
                    text = text[: m.start()] + marker + text[m.end() :]
            self._hidden[name] = hidden
            out[name] = text
        return out

    def restore(self, path: str, visible: str) -> str:
        if path not in self._hidden:
            self.visible_sources()
        for marker, block in self._hidden[path].items():
            if visible.count(marker) != 1:
                raise ValueError(f"{path}: an omitted-code marker was edited or removed")
            visible = visible.replace(marker, block)
        return visible

    def windows(self, runner: Runner | None = None) -> list[Window]:
        """Juliet files are short: one window per whole visible file, frames marked."""
        marks: dict[str, dict[int, str]] = {}
        f = self.finding
        for label, frames in (
            ("crash", f["frames"]),
            ("alloc", f["alloc_stack"]),
            ("free", f["free_stack"]),
        ):
            for fr in frames:
                if fr.get("file") and "/work/case/" in fr["file"] and fr.get("line"):
                    marks.setdefault(Path(fr["file"]).name, {}).setdefault(
                        fr["line"], f"{label}: {fr['function']}"
                    )
        out = []
        for name, text in self.visible_sources().items():
            n = len(text.splitlines())
            # Marks use original line numbers; bad() precedes the hidden blocks, so they hold.
            out.append(Window(name, 1, n, text, marks.get(name, {})))
        return out

    def build_description(self) -> str:
        lang = "C++" if self.data["lang"] == "c++" else "C"
        return (
            f"{lang} test case from NIST Juliet 1.3 ({self.data['cwe']}), compiled with clang "
            "-O0 and AddressSanitizer/LeakSanitizer/UBSan. Files listed are the whole program "
            "apart from Juliet's support library (io.c: printLine etc.). Tests: the program's "
            "behavior on its fixed input must not change."
        )

    # ---------------------------------------------------------------- containers
    def base_files(self) -> dict[str, bytes | Path]:
        files: dict[str, bytes | Path] = {
            f"case/{f}": JULIET / self.data["dir"] / f for f in self.data["files"]
        }
        files.update({f"support/{f}": JULIET / "testcasesupport" / f for f in SUPPORT})
        return files

    def prepare(self, runner: Runner) -> ImageRef:
        res = runner.run(
            IMAGES[getattr(runner, "name", "docker")],
            "mkdir -p bin out",
            files=self.base_files(),
            cwd="/work",
            network=False,
            timeout_s=120,
            save=True,
        )
        if res.image is None:
            raise RuntimeError(f"{self.id}: baseline checkpoint failed: {res.stderr[-500:]}")
        self._baseline = res.image
        return res.image

    def build_candidate(
        self, runner: Runner, baseline: ImageRef, files: dict[str, str]
    ) -> BuildResult:
        t0 = time.monotonic()
        res = runner.run(
            baseline,
            f"( {self.data['build_cmd_bad']} ) > /tmp/build.log 2>&1; rc=$?; "
            "tail -40 /tmp/build.log; exit $rc",
            files={f"case/{k}": v.encode() for k, v in files.items()},
            cwd="/work",
            network=False,
            timeout_s=180,
        )
        return BuildResult(res.exit_code == 0, res.stdout[-3000:], round(time.monotonic() - t0, 2))

    def cleanup(self, runner: Runner) -> None:
        if self._baseline is not None and hasattr(runner, "remove_image"):
            runner.remove_image(self._baseline)
            self._baseline = None
