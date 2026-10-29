"""Runner without containers, for the Render demo service (D-0061): one Linux box, no Docker.

An "image" is a directory snapshot; every run works in a fresh copy of it (save=True keeps the
copy as a new image). The guest path `cwd` (e.g. /work) maps to the copy's root, and files with
absolute guest paths under `cwd` land inside it.

Isolation, because candidate code is model-written C: when this process runs as root (the
service container does), commands run as `nobody` via `setpriv` with a cleared environment
(only the variables passed in `env`), no capabilities and no supplementary groups, so a
candidate binary can neither inherit the API key nor read it from the server's
/proc/<pid>/environ. Wall-clock timeouts kill the whole process group. Networking cannot be
switched off here; the demo runs fixed Juliet cases, and nothing secret is reachable.
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import tempfile
import time
import uuid
from pathlib import Path, PurePosixPath

from leakproof.runner.base import FileMap, ImageRef, RunResult

ROOT = Path(os.environ.get("LEAKPROOF_LOCAL_IMAGES", tempfile.gettempdir())) / "lp_images"
SAFE_PATH = "/usr/local/bin:/usr/bin:/bin"


FULL_DROP = [
    "setpriv",
    "--reuid=nobody",
    "--regid=nogroup",
    "--clear-groups",
    "--inh-caps=-all",
    "--bounding-set=-all",
    "--no-new-privs",
    "--",
]
# Some hosts (Render) refuse to change the bounding set. Switching from root to nobody with
# no-new-privs still leaves the child no capabilities and no way to regain any.
NO_BOUNDING = [a for a in FULL_DROP if not a.startswith("--bounding-set")]
DROP: list[str] = FULL_DROP
_isolation: str | None = None


def isolation() -> str:
    """ "nobody" when commands can run as `nobody`, else why not (probed once per process).

    A host that runs the container as root without CAP_SETUID/SETGID makes setpriv fail; the
    runner then runs commands as the server's own user with a cleared environment, and the demo
    service refuses live (model-written) runs (fail closed)."""
    global _isolation, DROP
    if _isolation is None:
        if os.name != "posix" or os.geteuid() != 0:
            _isolation = "not root: commands run as the server's user"
            return _isolation
        errors = []
        for variant in (FULL_DROP, NO_BOUNDING):
            try:
                r = subprocess.run([*variant, "/bin/true"], capture_output=True, timeout=10)
            except (OSError, subprocess.TimeoutExpired) as exc:
                errors.append(f"{type(exc).__name__}: {exc}")
                continue
            if r.returncode == 0:
                DROP, _isolation = variant, "nobody"
                return _isolation
            errors.append(r.stderr.decode(errors="replace").strip()[-200:])
        _isolation = "; ".join(errors)
    return _isolation


class LocalProcessRunner:
    name = "local"

    def __init__(self, **_: object) -> None:
        ROOT.mkdir(parents=True, exist_ok=True)

    def base(self) -> ImageRef:
        """An empty image (the toolchain is the host's)."""
        path = ROOT / "base"
        path.mkdir(parents=True, exist_ok=True)
        return ImageRef("local", str(path))

    def build_image(self, dockerfile: Path, context: Path, tag: str) -> ImageRef:
        raise NotImplementedError("the local runner has no image builds")

    def _guest(self, root: Path, guest: str, cwd: str) -> Path:
        p = PurePosixPath(guest)
        if p.is_absolute():
            try:
                p = p.relative_to(PurePosixPath(cwd))
            except ValueError as exc:
                raise ValueError(f"{guest}: the local runner only writes under {cwd}") from exc
        return root / Path(*p.parts)

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
        work = ROOT / f"run-{uuid.uuid4().hex[:12]}"
        shutil.copytree(image.ref, work)
        for guest, src in (files or {}).items():
            dest = self._guest(work, guest, cwd)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(src.read_bytes() if isinstance(src, Path) else src)
        shell = cmd if isinstance(cmd, str) else subprocess.list2cmdline(cmd)
        child_env = {"PATH": SAFE_PATH, "HOME": str(work), "LANG": "C.UTF-8"} | dict(env or {})
        argv = ["/bin/bash", "-c", shell]
        if isolation() == "nobody":
            shutil.chown(work, "nobody", "nogroup")
            for p in work.rglob("*"):
                shutil.chown(p, "nobody", "nogroup")
            argv = [*DROP, *argv]
        t0 = time.monotonic()
        timed_out = False
        proc = subprocess.Popen(
            argv,
            cwd=work,
            env=child_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        try:
            out, err = proc.communicate(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(proc.pid, signal.SIGKILL)
            out, err = proc.communicate()
        elapsed = time.monotonic() - t0
        saved = None
        if save:
            saved = ImageRef("local", str(work))
        else:
            shutil.rmtree(work, ignore_errors=True)
        return RunResult(
            exit_code=124 if timed_out else proc.returncode,
            stdout=out.decode(errors="replace"),
            stderr=err.decode(errors="replace"),
            elapsed_s=round(elapsed, 3),
            image=saved,
            max_rss_kb=None,
            timed_out=timed_out,
        )

    def read(self, image: ImageRef, guest_path: str) -> bytes:
        return self._guest(Path(image.ref), guest_path, "/work").read_bytes()

    def download(self, image: ImageRef, guest_path: str, local: Path) -> None:
        local.parent.mkdir(parents=True, exist_ok=True)
        local.write_bytes(self.read(image, guest_path))

    def remove_image(self, image: ImageRef) -> None:
        if image.ref.startswith(str(ROOT)) and Path(image.ref).name != "base":
            shutil.rmtree(image.ref, ignore_errors=True)
