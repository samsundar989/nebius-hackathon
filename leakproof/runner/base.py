"""The Runner interface: one contract, interchangeable backends (local Docker, Nebius Sandboxes)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

FileMap = dict[str, bytes | Path]


@dataclass(frozen=True)
class ImageRef:
    backend: str  # "docker" | "contree"
    ref: str  # docker tag/id, or contree image UUID

    def __str__(self) -> str:
        return f"{self.backend}:{self.ref}"


@dataclass
class RunResult:
    exit_code: int
    stdout: str
    stderr: str
    elapsed_s: float
    image: ImageRef | None = None  # set when save=True
    max_rss_kb: int | None = None  # docker: cgroup memory.peak; contree: process max_rss
    cost: float = 0.0  # USD, as reported by the backend (0 for local)
    timed_out: bool = False
    truncated: bool = False

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and not self.timed_out


class UnsupportedOption(RuntimeError):
    """The backend cannot honor a requested isolation/run option; never silently ignored."""


@runtime_checkable
class Runner(Protocol):
    name: str

    def build_image(self, dockerfile: Path, context: Path, tag: str) -> ImageRef: ...

    def run(
        self,
        image: ImageRef,
        cmd: list[str] | str,
        *,
        files: FileMap | None = None,
        env: dict[str, str] | None = None,
        cwd: str = "/work",
        timeout_s: int = 600,
        network: bool = True,
        save: bool = False,
    ) -> RunResult: ...

    def download(self, image: ImageRef, guest_path: str, local: Path) -> None: ...

    def read(self, image: ImageRef, guest_path: str) -> bytes: ...
