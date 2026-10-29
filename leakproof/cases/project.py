"""Bring-your-own project: any C/C++ tree described by a `leakproof.toml` (P5, D-0055).

    [project]
    name = "csvsplit"                       # becomes /src/<name> in the container
    src = "."                               # tree to copy, relative to this file
    image = "leakproof/cpp-sanitizers:e0"   # toolchain image (clang + sanitizer runtimes)
    build = "make"                          # $CC/$CFLAGS carry the sanitizer flags
    reproduce = "./csvsplit_fuzz poc.csv"   # must trip a sanitizer on the unpatched tree
    test = "make test"                      # optional
    harness = "csvsplit_fuzz"               # optional libFuzzer binary -> gate checks 5-7
    poc = "poc.csv"                         # optional input the harness reproduces with
    editable = ["src/*.c", "src/*.h"]       # optional globs; default: every source file

The case gives the fix loop and the gate the same hooks as an ARVO case, so a project with a
harness gets the full gate (differential, amplified refuzz, safe-fix); without one, checks 5-7
are reported as skipped.
"""

from __future__ import annotations

import fnmatch
import shlex
import time
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from leakproof.cases.arvo import ArvoCase
from leakproof.cases.base import BuildResult
from leakproof.findings import parse_report, primary
from leakproof.runner import ImageRef, Runner

SAN = "-fsanitize=address,undefined -fno-omit-frame-pointer -g -O0"
SKIP_DIRS = {".git", ".hg", "build", "out", "node_modules", "__pycache__"}
# quickjs.c is 2.1 MB; binaries and test media above this stay out of the copy.
MAX_FILE_BYTES = 8 * 1024 * 1024
TOOLCHAIN = {"docker": "leakproof/cpp-sanitizers:e0", "sandboxes": "tag:lp-cpp-sanitizers"}


@dataclass
class ProjectCase(ArvoCase):
    cfg: dict[str, Any] = field(default_factory=dict)
    root: Path = Path(".")

    @classmethod
    def load(cls, case_id: str) -> ProjectCase:  # type: ignore[override]
        # `project:<toml>#poc=<file>`: a batch fixes one cluster representative at a time.
        spec, _, poc = case_id.removeprefix("project:").partition("#poc=")
        path = Path(spec).resolve()
        cfg = tomllib.loads(path.read_text(encoding="utf-8"))["project"]
        if poc:
            cfg["poc"] = str(Path(poc).resolve())
        for key in ("name", "build", "reproduce"):
            if not cfg.get(key):
                raise ValueError(f"{path}: [project].{key} is required")
        return cls(
            id=f"project:{path}" + (f"#poc={Path(poc).resolve()}" if poc else ""),
            project=cfg["name"],
            image=cfg.get("image", ""),
            fuzz_target=cfg.get("harness") or "",
            crash_type="",
            fix_commit="",
            meta={"config": str(path)},
            suite="project",
            workdir=f"/src/{cfg['name']}",
            cfg=cfg,
            root=path.parent / cfg.get("src", "."),
        )

    # ------------------------------------------------------------------ gate hooks
    @property
    def tests_cmd(self) -> str | None:  # type: ignore[override]
        return self.cfg.get("test")

    @property
    def build_env(self) -> dict[str, str]:  # type: ignore[override]
        return {
            "CC": "clang",
            "CXX": "clang++",
            "CFLAGS": SAN,
            "CXXFLAGS": SAN,
            "LDFLAGS": "-fsanitize=address,undefined",
        }

    reproduce_env = {  # noqa: RUF012 - read-only
        "ASAN_OPTIONS": "detect_leaks=1:abort_on_error=0:symbolize=1",
        "UBSAN_OPTIONS": "print_stacktrace=1:halt_on_error=1",
    }

    @property
    def reproduce_cmd(self) -> str:  # type: ignore[override]
        return self.cfg["reproduce"]

    @property
    def harness_path(self) -> str | None:
        h = self.cfg.get("harness")
        return h if not h or h.startswith("/") else f"{self.workdir}/{h}"

    @property
    def artifact_path(self) -> str | None:
        a = self.cfg.get("artifact")
        return (a if a.startswith("/") else f"{self.workdir}/{a}") if a else self.harness_path

    def gate_build_cmd(self, files: dict[str, str]) -> str:
        # Copied-in files carry the host's mtime; touch them so make rebuilds (D-0041).
        touch = f"touch {shlex.join(sorted(files))}; " if files else ""
        return touch + self.cfg["build"]

    # ------------------------------------------------------------------ worker-visible view
    def _editable(self, path: str | None) -> bool:
        if not super()._editable(path):
            return False
        globs = self.cfg.get("editable")
        rel = path[len(self.src_root) :] if path else ""
        return not globs or any(fnmatch.fnmatch(rel, g) for g in globs)

    def build_description(self) -> str:
        tests = self.tests_cmd or "none configured"
        return (
            f"C/C++ project `{self.project}` (bring-your-own), built with `{self.cfg['build']}` "
            f"(clang, ASan+UBSan via $CFLAGS) in {self.workdir}. Project tests: {tests}."
        )

    # ------------------------------------------------------------------ baseline
    def _tree(self) -> dict[str, Path]:
        files: dict[str, Path] = {}
        for p in sorted(self.root.rglob("*")):
            rel = p.relative_to(self.root)
            if (
                p.is_file()
                and not SKIP_DIRS & set(rel.parts)
                and p.stat().st_size <= MAX_FILE_BYTES
            ):
                files[f"{self.workdir}/{rel.as_posix()}"] = p
        return files

    def prepare(self, runner: Runner) -> ImageRef:
        t0 = time.monotonic()
        kind = getattr(runner, "name", "docker")
        image = ImageRef(kind, self.image or TOOLCHAIN[kind])
        files: dict[str, Path | bytes] = dict(self._tree())
        if self.cfg.get("poc"):
            files["/tmp/poc"] = self.root / self.cfg["poc"]  # absolute paths stay absolute
        res = runner.run(
            image,
            f"{{ {self.cfg['build']} ; }} > /tmp/build.log 2>&1; rc=$?; tail -20 /tmp/build.log; "
            f"[ $rc = 0 ] || exit 97; {self.reproduce_cmd}",
            files=files,
            env=self.build_env | self.reproduce_env,
            cwd=self.workdir,
            timeout_s=1800,
            network=False,
            save=True,
        )
        self.prep.update(files=len(files), prepare_s=round(time.monotonic() - t0, 1))
        if res.exit_code == 97:
            raise RuntimeError(f"{self.id}: build failed:\n{res.stdout[-1500:]}")
        found = primary(parse_report(res.stderr + res.stdout))
        if found is None or res.image is None:
            raise RuntimeError(
                f"{self.id}: `reproduce` did not trip a sanitizer (exit {res.exit_code}):\n"
                f"{(res.stdout + res.stderr)[-1500:]}"
            )
        self.finding = found.to_dict(include_raw=False)
        self.prep["report_tail"] = (res.stderr + res.stdout)[-6000:]
        self._baseline = res.image
        return res.image

    def build_candidate(
        self, runner: Runner, baseline: ImageRef, files: dict[str, str]
    ) -> BuildResult:
        t0 = time.monotonic()
        res = runner.run(
            baseline,
            f"{{ {self.gate_build_cmd(files)} ; }} > /tmp/b.log 2>&1; rc=$?; "
            "grep -E 'error' /tmp/b.log | head -30; tail -15 /tmp/b.log; exit $rc",
            files={k: v.encode() for k, v in files.items()},
            env=self.build_env,
            cwd=self.workdir,
            timeout_s=1800,
            network=False,
        )
        return BuildResult(res.exit_code == 0, res.stdout[-3000:], round(time.monotonic() - t0, 2))

    def cleanup(self, runner: Runner) -> None:
        # Only our checkpoint: never the user's toolchain image.
        if self._baseline is not None and hasattr(runner, "remove_image"):
            runner.remove_image(self._baseline)
        self._baseline = None

    def record(self) -> dict[str, Any]:
        return {"id": self.id, "project": self.project, "config": self.cfg, "prep": self.prep}
