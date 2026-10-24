"""Nebius Sandboxes over plain REST (D-0053): the same Runner protocol as LocalDockerRunner.

Why not the SDK (leakproof/runner/contree.py): contree-sdk 0.3.6's spawn request has no
networking field, and the gate must run offline. The request shapes below are the SDK's own
(`contree_sdk/_internals/models`), plus `"networking": {"enabled": false}` from the docs.

  POST /v1/files                 upload bytes      -> {uuid, sha256}
  POST /v1/instances             spawn (one run)   -> {uuid: operation}
  POST /v1/images/import         import OCI ref    -> {uuid: operation}
  GET  /v1/operations/{uuid}     poll until SUCCESS | FAILED | CANCELLED
  GET  /v1/inspect/{uuid}/download?path=...        read a file from an image
Every run starts from an image uuid; `save=True` (disposable=false) returns the resulting image,
which is how the lineage baseline -> branch -> gate is recorded (`self.lineage`).
"""

from __future__ import annotations

import base64
import hashlib
import io
import shlex
import tarfile
import time
from pathlib import Path, PurePosixPath
from typing import Any

import httpx

from leakproof.config import SANDBOXES_BASE_URL, load_dotenv, require
from leakproof.llm.ledger import CostLedger, LedgerEntry
from leakproof.runner.base import FileMap, ImageRef, RunResult

FINAL = {"SUCCESS", "FAILED", "CANCELLED"}
TRUNCATE_AT = 4 * 1024 * 1024
BUNDLE = "/.lp_files.tar"  # many files travel as one upload, unpacked by the command


class SandboxesRestRunner:
    name = "sandboxes"

    def __init__(
        self,
        base_url: str = SANDBOXES_BASE_URL,
        http: httpx.Client | None = None,
        ledger: CostLedger | None = None,
        run_id: str = "sandboxes",
    ):
        load_dotenv()
        # Every run's reported cost goes into the ledger as kind=compute, `units` (not USD:
        # Sandboxes are not billed during the beta, ANSWER 0013 / D-0057), usd=0.
        self.ledger = ledger or CostLedger()
        self.run_id = run_id
        self.http = http or httpx.Client(
            base_url=base_url.removesuffix("/v1"),
            headers={
                "Authorization": f"Bearer {require('NEBIUS_API_KEY')}",
                "Project": require("NEBIUS_PROJECT_ID"),
            },
            timeout=60,
        )
        self.lineage: list[dict[str, Any]] = []  # one entry per saved run: parent -> child
        self._uploaded: dict[str, str] = {}  # sha256 -> file uuid

    # ------------------------------------------------------------------ plumbing
    def _json(self, method: str, path: str, **kw: Any) -> Any:
        for attempt in range(5):
            resp = self.http.request(method, path, **kw)
            if resp.status_code in (429, 502, 503, 504) and attempt < 4:
                time.sleep(min(2**attempt, 20))
                continue
            if resp.status_code >= 400:
                raise RuntimeError(f"{method} {path}: HTTP {resp.status_code} {resp.text[:400]}")
            return resp.json() if resp.content else None
        raise AssertionError("unreachable")

    def _wait(self, op: str, timeout_s: float) -> dict[str, Any]:
        t0, interval = time.monotonic(), 0.3
        while True:
            body = self._json("GET", f"/v1/operations/{op}")
            if body.get("status") in FINAL:
                return body
            if time.monotonic() - t0 > timeout_s + 60:
                self.http.delete(f"/v1/operations/{op}")
                raise TimeoutError(f"operation {op} still {body.get('status')} after {timeout_s}s")
            time.sleep(interval)
            interval = min(interval * 1.5, 5.0)

    def _upload(self, data: bytes) -> str:
        sha = hashlib.sha256(data).hexdigest()
        if sha not in self._uploaded:
            body = self._json(
                "POST",
                "/v1/files",
                content=data,
                headers={"Content-Type": "application/octet-stream"},
            )
            self._uploaded[sha] = body["uuid"]
        return self._uploaded[sha]

    @staticmethod
    def _bundle(files: FileMap, cwd: str) -> bytes:
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as tar:
            for guest, src in files.items():
                path = PurePosixPath(guest)
                if not path.is_absolute():
                    path = PurePosixPath(cwd) / path
                data = src.read_bytes() if isinstance(src, Path) else src
                info = tarfile.TarInfo(str(path).lstrip("/"))
                info.size, info.mode, info.mtime = len(data), 0o644, int(time.time())
                tar.addfile(info, io.BytesIO(data))
        return buf.getvalue()

    @staticmethod
    def _stream(desc: dict[str, Any] | None) -> tuple[str, bool]:
        if not desc:
            return "", False
        value = desc.get("value") or ""
        if desc.get("encoding", "base64") == "base64":
            value = base64.b64decode(value).decode(errors="replace")
        return value, bool(desc.get("truncated"))

    # ------------------------------------------------------------------ Runner protocol
    def import_image(self, oci_ref: str, tag: str | None = None, timeout_s: int = 3600) -> ImageRef:
        ref = oci_ref if "://" in oci_ref else f"docker://docker.io/{oci_ref}"
        t0 = time.monotonic()
        op = self._json(
            "POST",
            "/v1/images/import",
            json={"registry": {"url": ref}, "tag": tag, "timeout": timeout_s},
        )["uuid"]
        body = self._wait(op, timeout_s)
        if body.get("status") != "SUCCESS" or not (body.get("result") or {}).get("image"):
            raise RuntimeError(f"import {oci_ref} {body.get('status')}: {body.get('error')}")
        image = ImageRef("sandboxes", body["result"]["image"])
        self.lineage.append(
            {"op": "import", "from": oci_ref, "image": image.ref, "s": time.monotonic() - t0}
        )
        return image

    def build_image(self, dockerfile: Path, context: Path, tag: str) -> ImageRef:
        raise NotImplementedError("build images locally or import an OCI ref")

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
        spec_files = {}
        prefix = f"mkdir -p {shlex.quote(cwd)} && cd {shlex.quote(cwd)} && "
        if files:
            spec_files[BUNDLE] = {
                "uuid": self._upload(self._bundle(files, cwd)),
                "mode": "0644",
                "uid": 0,
                "gid": 0,
            }
            prefix = f"tar -xf {BUNDLE} -C / && rm -f {BUNDLE} && " + prefix
        request = {
            "command": prefix + shell_cmd,
            "image": image.ref,
            "hostname": "localhost",
            "args": [],
            "shell": True,
            "env": dict(env or {}),
            "cwd": "/",
            "disposable": not save,
            "timeout": int(timeout_s),
            "stdin": {"value": "", "encoding": "base64"},
            "files": spec_files,
            "truncate_output_at": TRUNCATE_AT,
            "preserve_env": False,
            "networking": {"enabled": bool(network)},
        }
        t0 = time.monotonic()
        op = self._json("POST", "/v1/instances", json=request)["uuid"]
        body = self._wait(op, timeout_s)
        meta = body.get("metadata") or {}
        res = meta.get("result") or {}
        state = res.get("state") or {}
        out, t_out = self._stream(res.get("stdout"))
        err, t_err = self._stream(res.get("stderr"))
        saved = None
        new_image = (body.get("result") or {}).get("image")
        if save and new_image:
            saved = ImageRef("sandboxes", new_image)
        cost = (res.get("resources") or {}).get("cost")
        # Every run, kept or disposable, with the image it started from: the checkpoint tree
        # (baseline -> one branch per worker build -> gate runs) the dashboard draws.
        self.lineage.append(
            {
                "op": "save" if saved else "run",
                "parent": image.ref,
                "image": saved.ref if saved else None,
                "network": bool(network),
                "exit": int(state.get("exit_code", -1)),
                "s": round(time.monotonic() - t0, 2),
                "usd": cost,
                "cmd": shell_cmd[:100],
            }
        )
        self.ledger.record(
            LedgerEntry(
                model="sandboxes",
                purpose="run" + (":save" if save else ""),
                run_id=self.run_id,
                prompt_tokens=0,
                completion_tokens=0,
                reasoning_tokens=0,
                usd=0.0,  # not billed during the beta (ANSWER 0013); the cost goes in units
                latency_s=round(time.monotonic() - t0, 3),
                kind="compute",
                units=float(cost or 0.0),
                note="sandbox_units, not billed during beta (billing page 2026-10-24): "
                + shell_cmd[:60],
            )
        )
        timed_out = bool(state.get("timed_out"))
        if body.get("status") != "SUCCESS" and not state:
            err = f"{err}\n[sandboxes] operation {body.get('status')}: {body.get('error')}"
        return RunResult(
            exit_code=124 if timed_out else int(state.get("exit_code", -1)),
            stdout=out,
            stderr=err,
            elapsed_s=round(time.monotonic() - t0, 3),
            image=saved,
            max_rss_kb=(res.get("resources") or {}).get("max_rss"),
            cost=cost,
            timed_out=timed_out,
            truncated=t_out or t_err,
        )

    def read(self, image: ImageRef, guest_path: str) -> bytes:
        resp = self.http.get(f"/v1/inspect/{image.ref}/download", params={"path": guest_path})
        if resp.status_code >= 400:
            raise RuntimeError(f"read {guest_path}: HTTP {resp.status_code} {resp.text[:200]}")
        return resp.content

    def download(self, image: ImageRef, guest_path: str, local: Path) -> None:
        local.parent.mkdir(parents=True, exist_ok=True)
        local.write_bytes(self.read(image, guest_path))

    def tag(self, image: ImageRef, tag: str) -> ImageRef:
        """Name an image; runs can then start from `tag:<name>`."""
        self._json("PATCH", f"/v1/images/{image.ref}/tag", json={"tag": tag})
        return ImageRef("sandboxes", f"tag:{tag}")

    def remove_image(self, image: ImageRef) -> None:
        """Sandboxes images are content-addressed layers; untagged ones need no cleanup here."""
        return None
