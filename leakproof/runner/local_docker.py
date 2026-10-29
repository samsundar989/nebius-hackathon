"""Local Docker backend.

Each run is `docker create` → copy files in (tar over `docker cp -`) → `docker start -a`, so
stdout/stderr stay separate. `save=True` commits the container to a content-named tag; branching
is simply N runs from the same tag. Peak memory comes from the container's cgroup `memory.peak`.
"""

from __future__ import annotations

import io
import os
import shlex
import subprocess
import tarfile
import time
import uuid
from pathlib import Path, PurePosixPath

from leakproof.runner.base import FileMap, ImageRef, RunResult

PEAK_FILE = "/.leakproof_mem_peak"


def _docker(*args: str, input: bytes | None = None, timeout: float | None = None) -> bytes:
    proc = subprocess.run(
        ["docker", *args], input=input, capture_output=True, timeout=timeout, check=False
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"docker {args[0]} failed ({proc.returncode}): {proc.stderr.decode(errors='replace')}"
        )
    return proc.stdout


def _tar_files(files: FileMap, cwd: str) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for guest, src in files.items():
            path = PurePosixPath(guest)
            if not path.is_absolute():
                path = PurePosixPath(cwd) / path
            data = src.read_bytes() if isinstance(src, Path) else src
            info = tarfile.TarInfo(str(path).lstrip("/"))
            info.size = len(data)
            info.mode = 0o755 if isinstance(src, Path) and src.stat().st_mode & 0o111 else 0o644
            info.mtime = int(time.time())
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


class LocalDockerRunner:
    name = "docker"

    def __init__(
        self,
        memory: str | None = None,
        cpus: float | None = None,
        gpus: bool = False,
        snapshot_repo: str = "leakproof/snap",
    ) -> None:
        # Defaults 4g / 2 CPUs; LEAKPROOF_DOCKER_MEMORY / _CPUS raise them for a large project
        # (a C++ library under ASan), and reach the gate's own process through the environment.
        self.memory = memory or os.environ.get("LEAKPROOF_DOCKER_MEMORY", "4g")
        self.cpus = cpus or float(os.environ.get("LEAKPROOF_DOCKER_CPUS", "2"))
        self.gpus = gpus
        self.snapshot_repo = snapshot_repo

    def build_image(self, dockerfile: Path, context: Path, tag: str) -> ImageRef:
        _docker("build", "-q", "-t", tag, "-f", str(dockerfile), str(context))
        return ImageRef("docker", tag)

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
    ) -> RunResult:
        shell_cmd = cmd if isinstance(cmd, str) else shlex.join(cmd)
        # Record cgroup v2 peak memory after the command, preserving its exit code.
        wrapped = (
            f"( {shell_cmd} ); rc=$?; "
            f"cat /sys/fs/cgroup/memory.peak > {PEAK_FILE} 2>/dev/null; exit $rc"
        )
        name = f"leakproof-{uuid.uuid4().hex[:12]}"
        create = ["create", "--name", name, "-w", cwd, f"--memory={self.memory}"]
        create += [f"--cpus={self.cpus}"]
        if not network:
            create.append("--network=none")
        if self.gpus:
            create += ["--gpus", "all"]
        for key, value in (env or {}).items():
            create += ["-e", f"{key}={value}"]
        create += ["--entrypoint", "/bin/sh", image.ref, "-c", wrapped]
        _docker(*create)
        try:
            if files:
                _docker("cp", "-", f"{name}:/", input=_tar_files(files, cwd))
            t0 = time.monotonic()
            timed_out = False
            try:
                proc = subprocess.run(
                    ["docker", "start", "-a", name],
                    capture_output=True,
                    timeout=timeout_s,
                    check=False,
                )
                stdout, stderr = proc.stdout, proc.stderr
            except subprocess.TimeoutExpired as exc:
                timed_out = True
                subprocess.run(["docker", "kill", name], capture_output=True, check=False)
                stdout, stderr = exc.stdout or b"", exc.stderr or b""
            elapsed = time.monotonic() - t0
            state = _docker("inspect", "-f", "{{.State.ExitCode}}", name).decode().strip()
            exit_code = 124 if timed_out else int(state)
            peak = self._read_peak(name)
            saved = None
            if save:
                image_id = _docker("commit", name).decode().strip()
                tag = f"{self.snapshot_repo}:{image_id.split(':')[-1][:16]}"
                _docker("tag", image_id, tag)
                saved = ImageRef("docker", tag)
            return RunResult(
                exit_code=exit_code,
                stdout=stdout.decode(errors="replace"),
                stderr=stderr.decode(errors="replace"),
                elapsed_s=round(elapsed, 3),
                image=saved,
                max_rss_kb=peak,
                timed_out=timed_out,
            )
        finally:
            subprocess.run(["docker", "rm", "-f", name], capture_output=True, check=False)

    @staticmethod
    def _read_peak(container: str) -> int | None:
        try:
            raw = _docker("cp", f"{container}:{PEAK_FILE}", "-")
            with tarfile.open(fileobj=io.BytesIO(raw)) as tar:
                member = tar.next()
                fh = tar.extractfile(member) if member else None
                return int(fh.read().strip()) // 1024 if fh else None
        except (RuntimeError, ValueError, tarfile.TarError):
            return None

    def _with_container(self, image: ImageRef):  # noqa: ANN202 - small context helper
        name = f"leakproof-ro-{uuid.uuid4().hex[:12]}"
        _docker("create", "--name", name, "--entrypoint", "/bin/true", image.ref)
        return name

    def download(self, image: ImageRef, guest_path: str, local: Path) -> None:
        name = self._with_container(image)
        try:
            local.parent.mkdir(parents=True, exist_ok=True)
            _docker("cp", f"{name}:{guest_path}", str(local))
        finally:
            subprocess.run(["docker", "rm", "-f", name], capture_output=True, check=False)

    def read(self, image: ImageRef, guest_path: str) -> bytes:
        name = self._with_container(image)
        try:
            raw = _docker("cp", f"{name}:{guest_path}", "-")
        finally:
            subprocess.run(["docker", "rm", "-f", name], capture_output=True, check=False)
        with tarfile.open(fileobj=io.BytesIO(raw)) as tar:
            member = tar.next()
            if member is None or not member.isfile():
                raise IsADirectoryError(guest_path)
            fh = tar.extractfile(member)
            assert fh is not None
            return fh.read()

    def remove_image(self, image: ImageRef) -> None:
        subprocess.run(["docker", "rmi", "-f", image.ref], capture_output=True, check=False)
