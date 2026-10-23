"""Fan out N workers from one baseline checkpoint; each candidate builds in its own container."""

from __future__ import annotations

import concurrent.futures as cf
from typing import Any

from leakproof.cases.base import Case, Window
from leakproof.llm import LLMClient
from leakproof.runner import ImageRef, Runner
from leakproof.worker import Candidate, run_worker

MAX_PARALLEL = 4


def fan_out(
    client: LLMClient,
    runner: Runner,
    case: Case,
    baseline: ImageRef,
    *,
    root_cause: str,
    hypotheses: list[dict[str, Any]],
    sources: dict[str, str],
    windows: list[Window],
    model: str = "lightning",
    parallel: int = MAX_PARALLEL,
) -> list[Candidate]:
    def one(i: int, hyp: dict[str, Any]) -> Candidate:
        return run_worker(
            client,
            index=i,
            finding=case.finding,
            root_cause=root_cause,
            hypothesis=hyp,
            sources=sources,
            windows=windows,
            restore=case.restore,
            build=lambda files: case.build_candidate(runner, baseline, files),
            model=model,
        )

    with cf.ThreadPoolExecutor(min(parallel, MAX_PARALLEL)) as pool:
        futures = [pool.submit(one, i, h) for i, h in enumerate(hypotheses)]
        return [f.result() for f in futures]
