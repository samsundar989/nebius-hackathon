"""Runner contract: every backend must pass these. Docker runs locally; Contree skips with the
/whoami reason until Sandboxes access is approved."""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest

from leakproof.runner import ImageRef, LocalDockerRunner, Runner, UnsupportedOption

BASE = "ubuntu:22.04"


def _docker_available() -> bool:
    if not shutil.which("docker"):
        return False
    return subprocess.run(["docker", "info"], capture_output=True, check=False).returncode == 0


@pytest.fixture(scope="module", params=["docker", "contree"])
def backend(request: pytest.FixtureRequest) -> Iterator[tuple[Runner, ImageRef]]:
    if request.param == "docker":
        if not _docker_available():
            pytest.skip("docker engine not available")
        request.applymarker(pytest.mark.docker)
        subprocess.run(["docker", "pull", "-q", BASE], capture_output=True, check=True)
        yield LocalDockerRunner(memory="1g", cpus=1), ImageRef("docker", BASE)
    else:
        from leakproof.runner.contree import ContreeRunner, access_status

        ok, why = access_status()
        if not ok:
            pytest.skip(f"Contree not usable: {why}")
        runner = ContreeRunner()
        yield runner, runner.import_image(BASE)


pytestmark = [pytest.mark.docker, pytest.mark.contree]


def test_stdout_stderr_exit(backend: tuple[Runner, ImageRef]) -> None:
    runner, image = backend
    r = runner.run(image, "echo out; echo err >&2; exit 3", timeout_s=60)
    assert r.exit_code == 3 and not r.ok
    assert r.stdout.strip() == "out" and r.stderr.strip() == "err"
    assert r.elapsed_s >= 0


def test_list_command_is_quoted(backend: tuple[Runner, ImageRef]) -> None:
    runner, image = backend
    r = runner.run(image, ["printf", "%s|", "a b", "c;d"], timeout_s=60)
    assert r.ok and r.stdout == "a b|c;d|"


def test_files_env_cwd(backend: tuple[Runner, ImageRef], tmp_path: Path) -> None:
    runner, image = backend
    local = tmp_path / "host.txt"
    local.write_text("from-path\n")
    r = runner.run(
        image,
        "pwd; cat rel.txt /etc/abs.txt sub/host.txt; echo $LP_VAR",
        files={"rel.txt": b"rel\n", "/etc/abs.txt": b"abs\n", "sub/host.txt": local},
        env={"LP_VAR": "hello env"},
        cwd="/work/case",
        timeout_s=60,
    )
    assert r.ok, r.stderr
    assert r.stdout.split("\n") == ["/work/case", "rel", "abs", "from-path", "hello env", ""]


def test_timeout(backend: tuple[Runner, ImageRef]) -> None:
    runner, image = backend
    r = runner.run(image, "sleep 30", timeout_s=2)
    assert r.timed_out and not r.ok


def test_network_off(backend: tuple[Runner, ImageRef]) -> None:
    runner, image = backend
    try:
        r = runner.run(image, "ls /sys/class/net", network=False, timeout_s=60)
    except UnsupportedOption:
        pytest.skip(f"{runner.name} cannot isolate networking (raises UnsupportedOption)")
    assert r.ok and r.stdout.split() == ["lo"]


def test_save_branch_read_download(backend: tuple[Runner, ImageRef], tmp_path: Path) -> None:
    runner, image = backend
    base = runner.run(image, "mkdir -p /state && echo v1 > /state/f", save=True, timeout_s=60)
    assert base.ok and base.image is not None
    # Branch twice from the same checkpoint; each branch must see v1 and not the other's write.
    a = runner.run(base.image, "cat /state/f; echo a > /state/a", save=True, timeout_s=60)
    b = runner.run(base.image, "cat /state/f; ls /state", save=True, timeout_s=60)
    assert a.stdout.strip() == "v1" and b.stdout.split() == ["v1", "f"]
    assert a.image and b.image and a.image != b.image
    assert runner.read(a.image, "/state/a") == b"a\n"
    runner.download(base.image, "/state/f", tmp_path / "out" / "f")
    assert (tmp_path / "out" / "f").read_text() == "v1\n"


def test_disposable_by_default(backend: tuple[Runner, ImageRef]) -> None:
    runner, image = backend
    r = runner.run(image, "echo x > /tmp/x", timeout_s=60)
    assert r.ok and r.image is None


def test_reports_peak_memory(backend: tuple[Runner, ImageRef]) -> None:
    runner, image = backend
    r = runner.run(image, "head -c 50000000 /dev/zero | tail -c 1 > /dev/null", timeout_s=60)
    assert r.ok and r.max_rss_kb is not None and r.max_rss_kb > 0


def test_build_image(backend: tuple[Runner, ImageRef], tmp_path: Path) -> None:
    runner, _ = backend
    (tmp_path / "payload.txt").write_text("copied\n")
    (tmp_path / "Dockerfile").write_text(
        f"FROM {BASE}\nENV LP_BUILT=yes\nCOPY payload.txt /opt/payload.txt\n"
        "RUN echo built > /opt/marker\nWORKDIR /work\n"
    )
    ref = runner.build_image(tmp_path / "Dockerfile", tmp_path, "leakproof/contract-test:latest")
    r = runner.run(ref, "cat /opt/marker /opt/payload.txt; echo $LP_BUILT", timeout_s=60)
    assert r.ok and r.stdout.split() == ["built", "copied", "yes"]
