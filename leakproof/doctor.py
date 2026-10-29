"""`leakproof doctor`: is this machine ready to run `leakproof fix`? (review #17 order 5)

One PASS / WARN / FAIL line per check, each failure with the fix. Never prints a key's value:
only whether it is set and whether Token Factory accepts it (GET /models, no model call, $0).

  docker      the Docker CLI answers and the engine is running
  image       the toolchain image (leakproof/cpp-sanitizers:e0) exists, or how to build it
  key         NEBIUS_API_KEY set and accepted by Token Factory
  project     NEBIUS_PROJECT_ID set (needed for Sandboxes; optional for Docker runs)
  budget      LEAKPROOF_BUDGET_USD, and the ledger total against LEAKPROOF_LEDGER_CAP_USD
  sandboxes   optional: the Sandboxes whoami endpoint, when a project id is set
  config      optional: a leakproof.toml parses and has the required fields
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tomllib
import urllib.error
import urllib.request
from pathlib import Path

from leakproof.cases.project import TOOLCHAIN
from leakproof.config import REPO_ROOT, SANDBOXES_BASE_URL, TF_BASE_URL, budget_usd, load_dotenv
from leakproof.llm.ledger import CostLedger

IMAGE = TOOLCHAIN["docker"]
FIELDS = ("name", "build", "reproduce")
KNOWN = {"name", "src", "image", "build", "reproduce", "test", "harness", "poc", "artifact"}
KNOWN |= {"editable"}


def _line(status: str, name: str, detail: str, fix: str = "") -> str:
    return f"{status:<4}  {name:<9}  {detail}" + (f"\n            fix: {fix}" if fix else "")


def _get(url: str, headers: dict[str, str], timeout: float = 15) -> int:
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status
    except urllib.error.HTTPError as exc:
        return exc.code


def check_docker() -> list[tuple[str, str, str, str]]:
    if shutil.which("docker") is None:
        return [("FAIL", "docker", "no `docker` on PATH", "install Docker Desktop / Docker Engine")]
    r = subprocess.run(["docker", "info", "--format", "{{.ServerVersion}}"], capture_output=True)
    if r.returncode != 0:
        return [("FAIL", "docker", "the Docker engine is not running", "start Docker, then retry")]
    out = [("PASS", "docker", f"engine {r.stdout.decode().strip()}", "")]
    img = subprocess.run(["docker", "image", "inspect", IMAGE], capture_output=True)
    out.append(
        ("PASS", "image", IMAGE, "")
        if img.returncode == 0
        else (
            "FAIL",
            "image",
            f"{IMAGE} is not built",
            f"docker build -t {IMAGE} {REPO_ROOT / 'images' / 'cpp-sanitizers'}",
        )
    )
    return out


def check_keys() -> list[tuple[str, str, str, str]]:
    out = []
    key = os.environ.get("NEBIUS_API_KEY", "")
    if not key:
        out.append(
            (
                "FAIL",
                "key",
                "NEBIUS_API_KEY is not set",
                "put it in .env (see .env.example); create one in the Token Factory console",
            )
        )
    else:
        base = os.environ.get("TF_BASE_URL", TF_BASE_URL).rstrip("/")
        try:
            code = _get(f"{base}/models", {"Authorization": f"Bearer {key}"})
        except OSError as exc:
            code, why = 0, type(exc).__name__
        if code == 200:
            out.append(("PASS", "key", "set; Token Factory accepts it (GET /models)", ""))
        elif code in (401, 403):
            out.append(
                ("FAIL", "key", f"set, but Token Factory answered {code}", "create a new key")
            )
        else:
            detail = f"HTTP {code}" if code else why
            out.append(("WARN", "key", f"set; Token Factory not reachable ({detail})", ""))
    project = os.environ.get("NEBIUS_PROJECT_ID", "")
    out.append(
        ("PASS", "project", "NEBIUS_PROJECT_ID set", "")
        if project
        else (
            "WARN",
            "project",
            "NEBIUS_PROJECT_ID not set (only `--runner sandboxes` needs it)",
            "",
        )
    )
    if key and project:
        try:
            code = _get(
                f"{SANDBOXES_BASE_URL.rstrip('/')}/whoami",
                {"Authorization": f"Bearer {key}", "Project": project},
            )
        except OSError:
            code = 0
        out.append(
            ("PASS", "sandboxes", "Nebius Sandboxes accepts this key and project", "")
            if code == 200
            else (
                "WARN",
                "sandboxes",
                f"Sandboxes whoami answered {code or 'nothing'} (Docker runs do not need it)",
                "",
            )
        )
    return out


def check_budget() -> list[tuple[str, str, str, str]]:
    ledger = CostLedger()
    total = ledger.file_total()
    run_cap = budget_usd()
    out = [("PASS", "budget", f"per-process cap ${run_cap:.2f} (LEAKPROOF_BUDGET_USD)", "")]
    if ledger.ledger_cap is None:
        out.append(("PASS", "ledger", f"${total:.4f} recorded in {ledger.path.name}; no cap", ""))
    elif total >= ledger.ledger_cap:
        out.append(
            (
                "FAIL",
                "ledger",
                f"${total:.4f} recorded, at or over LEAKPROOF_LEDGER_CAP_USD=${ledger.ledger_cap:.2f}",
                "raise the cap in .env if you mean to spend more",
            )
        )
    else:
        left = ledger.ledger_cap - total
        out.append(
            ("PASS", "ledger", f"${total:.4f} of ${ledger.ledger_cap:.2f}; ${left:.2f} left", "")
        )
    return out


def check_config(path: Path) -> list[tuple[str, str, str, str]]:
    if not path.is_file():
        return [("WARN", "config", f"no {path.name} here", "leakproof init <repo-dir> drafts one")]
    try:
        cfg = tomllib.loads(path.read_text(encoding="utf-8")).get("project")
    except tomllib.TOMLDecodeError as exc:
        return [("FAIL", "config", f"{path}: not valid TOML ({exc})", "")]
    if not isinstance(cfg, dict):
        return [("FAIL", "config", f"{path}: no [project] table", "start the file with [project]")]
    missing = [k for k in FIELDS if not cfg.get(k)]
    if missing:
        return [
            ("FAIL", "config", f"{path}: missing {', '.join(missing)}", "see docs/WALKTHROUGH.md")
        ]
    unknown = sorted(set(cfg) - KNOWN)
    src = (path.parent / cfg.get("src", ".")).resolve()
    out = [("PASS", "config", f"{path.name}: {cfg['name']}, source {src}", "")]
    if unknown:
        out.append(("WARN", "config", f"unknown keys ignored: {', '.join(unknown)}", ""))
    if not src.is_dir():
        out.append(("FAIL", "config", f"src {src} does not exist", "fix `src` in the config"))
    return out


def doctor(config: Path | None = None) -> int:
    load_dotenv()
    rows = check_docker() + check_keys() + check_budget()
    if config is not None:
        rows += check_config(config)
    for r in rows:
        print(_line(*r))
    failed = sum(r[0] == "FAIL" for r in rows)
    print(f"\n{'ready' if not failed else f'{failed} problem(s) to fix'}")
    return 1 if failed else 0
