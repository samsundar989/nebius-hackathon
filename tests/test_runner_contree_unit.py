"""ContreeRunner request mapping, against a fake SDK client (no network)."""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace
from typing import Any

import pytest

from leakproof.runner import ImageRef, UnsupportedOption
from leakproof.runner.contree import ContreeRunner, _exports, _parse_dockerfile, _parse_env


class FakeImage:
    def __init__(self, log: list[dict[str, Any]], uuid: str = "u-base") -> None:
        self.log, self.uuid = log, uuid

    def run(self, **kwargs: Any) -> FakeImage:
        self.log.append(kwargs)
        return self

    def wait(self) -> SimpleNamespace:
        res = SimpleNamespace(
            exit_code=0,
            stdout="ok",
            stderr="",
            elapsed_time=timedelta(seconds=1.5),
            cost=0.0,
            truncated=False,
            _raw=None,
        )
        return SimpleNamespace(result=res, uuid="u-saved")


@pytest.fixture
def fake() -> tuple[ContreeRunner, list[dict[str, Any]]]:
    log: list[dict[str, Any]] = []
    client = SimpleNamespace(images=SimpleNamespace(use=lambda ref: FakeImage(log)))
    return ContreeRunner(client=client), log


def test_disposable_unless_saved(fake: tuple[ContreeRunner, list[dict[str, Any]]]) -> None:
    runner, log = fake
    r1 = runner.run(ImageRef("contree", "u-base"), ["echo", "a b"], cwd="/w")
    r2 = runner.run(ImageRef("contree", "u-base"), "true", save=True)
    assert log[0]["disposable"] is True and log[1]["disposable"] is False
    assert "cd /w && echo 'a b'" in log[0]["shell"]
    assert r1.image is None and r2.image == ImageRef("contree", "u-saved")
    assert r1.elapsed_s == 1.5


def test_refuses_network_off(fake: tuple[ContreeRunner, list[dict[str, Any]]]) -> None:
    runner, log = fake
    with pytest.raises(UnsupportedOption):
        runner.run(ImageRef("contree", "u-base"), "true", network=False)
    assert log == []


def test_parse_dockerfile_continuations() -> None:
    text = '# c\nFROM x:1\nRUN a \\\n    && b\nENV A=1 B="two words"\nENV C 3\n'
    assert _parse_dockerfile(text) == [
        ("FROM", "x:1"),
        ("RUN", "a && b"),
        ("ENV", 'A=1 B="two words"'),
        ("ENV", "C 3"),
    ]
    assert _parse_env('A=1 B="two words"') == {"A": "1", "B": "two words"}
    assert _parse_env("C 3") == {"C": "3"}


def test_exports_keep_guest_expansion() -> None:
    assert _exports({"PATH": "/opt/bin:${PATH}"}) == 'export PATH="/opt/bin:${PATH}"; '
