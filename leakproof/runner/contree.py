"""Nebius Sandboxes (Contree) backend, via contree-sdk 0.3.6.

Notes measured against the SDK source (see docs/FEEDBACK.md → Sandboxes):
- `run()` defaults to `disposable=True`; we pass `disposable=not save`.
- 0.3.6's spawn request has no networking field, so `network=False` cannot be honored and raises
  UnsupportedOption instead of silently running with a NIC (the gate depends on isolation).
- There is no Dockerfile build in the SDK; `build_image` replays a simple Dockerfile
  (FROM / RUN / ENV / WORKDIR / COPY / ARG) as a chain of saved runs.
- Image ENV is only applied with shell=True, so commands always go through the shell.
"""

from __future__ import annotations

import shlex
from pathlib import Path
from typing import Any

import httpx

from leakproof.config import SANDBOXES_BASE_URL, load_dotenv, require
from leakproof.runner.base import FileMap, ImageRef, RunResult, UnsupportedOption


def whoami() -> tuple[int, dict[str, Any]]:
    """(HTTP status, body) of GET /whoami; never raises for HTTP errors."""
    load_dotenv()
    resp = httpx.get(
        f"{SANDBOXES_BASE_URL}/whoami",
        headers={
            "Authorization": f"Bearer {require('NEBIUS_API_KEY')}",
            "Project": require("NEBIUS_PROJECT_ID"),
        },
        timeout=30,
    )
    try:
        body = resp.json()
    except ValueError:
        body = {"text": resp.text[:500]}
    return resp.status_code, body


def access_status() -> tuple[bool, str]:
    """Whether this key/project may spawn sandboxes, and a human-readable reason."""
    try:
        status, body = whoami()
    except (RuntimeError, httpx.HTTPError) as exc:
        return False, f"whoami failed: {exc}"
    if status == 403:
        return False, "403 on /whoami: Sandboxes beta not approved yet"
    if status != 200:
        return False, f"HTTP {status} on /whoami"
    perms = body.get("permissions", {})
    if not perms.get("spawn"):
        granted = sorted(k for k, v in perms.items() if v)
        return False, f"200 on /whoami but spawn permission is false (granted: {granted or 'none'})"
    return True, "ok"


class ContreeRunner:
    name = "contree"

    def __init__(self, client: Any | None = None) -> None:
        load_dotenv()
        if client is None:
            from contree_sdk import ContreeSync

            client = ContreeSync()  # IAMAuth reads NEBIUS_API_KEY + NEBIUS_PROJECT_ID
        self.client = client
        self._env: dict[str, dict[str, str]] = {}  # image uuid -> ENV from build_image

    # -------------------------------------------------------------- images
    def import_image(self, oci_ref: str, tag: str | None = None) -> ImageRef:
        img = self.client.images.oci(oci_ref, tag=tag)
        return ImageRef("contree", str(img.uuid))

    def build_image(self, dockerfile: Path, context: Path, tag: str) -> ImageRef:
        image: ImageRef | None = None
        env: dict[str, str] = {}
        workdir = "/"
        for instr, arg in _parse_dockerfile(dockerfile.read_text()):
            if instr == "FROM":
                image = self.import_image(arg.split()[0])
            elif image is None:
                if instr == "ARG":
                    continue
                raise ValueError(f"{instr} before FROM in {dockerfile}")
            elif instr == "RUN":
                res = self.run(image, _exports(env) + arg, cwd=workdir, timeout_s=3600, save=True)
                if not res.ok or res.image is None:
                    raise RuntimeError(f"RUN failed ({res.exit_code}): {res.stderr[-2000:]}")
                image = res.image
            elif instr == "ENV":
                env.update(_parse_env(arg))
            elif instr == "WORKDIR":
                workdir = arg.strip()
                res = self.run(image, f"mkdir -p {shlex.quote(workdir)}", save=True)
                image = res.image or image
            elif instr == "COPY":
                *srcs, dest = shlex.split(arg)
                files: FileMap = {}
                for src in srcs:
                    for path in _expand(context / src):
                        rel = path.relative_to(context / src) if (context / src).is_dir() else None
                        target = (
                            f"{dest.rstrip('/')}/{rel or path.name}"
                            if dest.endswith("/") or rel
                            else dest
                        )
                        files[target] = path
                res = self.run(image, "true", files=files, save=True)
                image = res.image or image
            elif instr in {"ARG", "LABEL", "CMD", "ENTRYPOINT", "EXPOSE", "USER", "SHELL"}:
                continue  # Contree drops ENTRYPOINT/CMD on import; others are irrelevant here
            else:
                raise ValueError(f"unsupported Dockerfile instruction {instr}")
        if image is None:
            raise ValueError(f"no FROM in {dockerfile}")
        self.client.images.use(image.ref).tag_as(tag)
        self._env[image.ref] = env
        return image

    # -------------------------------------------------------------- runs
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
        if not network:
            raise UnsupportedOption(
                "contree-sdk 0.3.6 cannot disable networking per run; refusing to run "
                "a network-isolated step with a NIC"
            )
        shell_cmd = cmd if isinstance(cmd, str) else shlex.join(cmd)
        build_env = _exports(self._env.get(image.ref, {}))
        img = self.client.images.use(image.ref)
        done = img.run(
            shell=f"{build_env}mkdir -p {shlex.quote(cwd)} && cd {shlex.quote(cwd)} && {shell_cmd}",
            env=dict(env or {}),
            files={k: v for k, v in (files or {}).items()},
            timeout=timeout_s,
            disposable=not save,
            stdout=str,
            stderr=str,
        ).wait()
        result = done.result
        raw = getattr(result, "_raw", None)
        resources = raw.result.resources if raw is not None and raw.result else None
        state = raw.result.state if raw is not None and raw.result else None
        return RunResult(
            exit_code=result.exit_code,
            stdout=result.stdout or "",
            stderr=result.stderr or "",
            elapsed_s=result.elapsed_time.total_seconds(),
            image=ImageRef("contree", str(done.uuid)) if save and done.uuid else None,
            max_rss_kb=getattr(resources, "max_rss", None),
            cost=result.cost,
            timed_out=bool(getattr(state, "timed_out", False)),
            truncated=result.truncated,
        )

    def download(self, image: ImageRef, guest_path: str, local: Path) -> None:
        local.parent.mkdir(parents=True, exist_ok=True)
        self.client.images.use(image.ref).download(guest_path, local)

    def read(self, image: ImageRef, guest_path: str) -> bytes:
        return self.client.images.use(image.ref).read(guest_path)


def _parse_dockerfile(text: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    buf = ""
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.endswith("\\"):
            buf += stripped[:-1].rstrip() + " "
            continue
        full = (buf + stripped).strip()
        buf = ""
        instr, _, arg = full.partition(" ")
        out.append((instr.upper(), arg.strip()))
    return out


def _parse_env(arg: str) -> dict[str, str]:
    parts = shlex.split(arg)
    if len(parts) >= 2 and "=" not in parts[0]:
        return {parts[0]: " ".join(parts[1:])}
    env = {}
    for part in parts:
        key, _, value = part.partition("=")
        env[key] = value  # may reference $VARS; expanded by the guest shell, see _exports
    return env


def _exports(env: dict[str, str]) -> str:
    """Shell prefix exporting Dockerfile ENV so `${PATH}`-style references expand in the guest."""
    out = ""
    for key, value in env.items():
        escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("`", "\\`")
        out += f'export {key}="{escaped}"; '
    return out


def _expand(path: Path) -> list[Path]:
    if path.is_dir():
        return sorted(p for p in path.rglob("*") if p.is_file())
    return [path]
