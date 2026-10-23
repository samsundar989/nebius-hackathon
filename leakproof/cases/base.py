"""What the fix loop needs from a case, whatever suite it comes from (Juliet, ARVO).

The worker side sees only `visible_sources()`; build flags, PoC, tests and the gate's commands
stay in the suite modules and in `leakproof/gate.py`, which runs as a separate process.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from leakproof.runner import ImageRef, Runner


@dataclass
class BuildResult:
    ok: bool
    log_tail: str
    elapsed_s: float


@dataclass
class Window:
    path: str
    start: int  # 1-based, inclusive
    end: int
    text: str
    marks: dict[int, str] = field(default_factory=dict)  # line -> why it matters


class Case(Protocol):
    id: str
    suite: str  # juliet | arvo
    project: str
    finding: dict[str, Any]  # the reproduced finding (Finding.to_dict without raw)

    def prepare(self, runner: Runner) -> ImageRef:
        """Build/reproduce the baseline and return the checkpoint every branch starts from."""
        ...

    def visible_sources(self, runner: Runner) -> dict[str, str]:
        """{path: text} the planner and workers may read and edit (full files)."""
        ...

    def windows(self, runner: Runner) -> list[Window]:
        """Source windows around the crash/alloc/free frames."""
        ...

    def build_description(self) -> str:
        """One paragraph for the planner: language, build system, what tests exist."""
        ...

    def restore(self, path: str, visible: str) -> str:
        """Map an edited visible file back to the full file written into the container."""
        ...

    def build_candidate(
        self, runner: Runner, baseline: ImageRef, files: dict[str, str]
    ) -> BuildResult:
        """Compile a candidate (no PoC, no tests): compiler feedback for the worker."""
        ...

    def cleanup(self, runner: Runner) -> None: ...
