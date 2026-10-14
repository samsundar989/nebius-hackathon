"""Execution backends behind one interface (see base.Runner)."""

from leakproof.runner.base import FileMap, ImageRef, Runner, RunResult, UnsupportedOption
from leakproof.runner.local_docker import LocalDockerRunner

__all__ = [
    "FileMap",
    "ImageRef",
    "LocalDockerRunner",
    "RunResult",
    "Runner",
    "UnsupportedOption",
    "get_runner",
]


def get_runner(name: str = "docker", **kwargs: object) -> Runner:
    if name == "docker":
        return LocalDockerRunner(**kwargs)  # type: ignore[arg-type]
    if name == "contree":
        from leakproof.runner.contree import ContreeRunner

        return ContreeRunner(**kwargs)  # type: ignore[arg-type]
    raise ValueError(f"unknown runner {name!r}")
