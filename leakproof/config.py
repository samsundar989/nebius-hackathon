"""Environment loading. Secrets come only from the process env or a gitignored .env file."""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
# Queued jobs run from a snapshot copy; LEAKPROOF_RUNS points results and the cost ledger at
# the live checkout so nothing lands in the disposable snapshot.
RUNS_DIR = Path(os.environ.get("LEAKPROOF_RUNS", REPO_ROOT / "runs"))
# Datasets fetched by scripts (Juliet tree, arvo.db). Not in the repo.
CACHE_DIR = Path(os.environ.get("LEAKPROOF_CACHE", Path.home() / ".cache" / "leakproof"))
TF_BASE_URL = "https://api.tokenfactory.nebius.com/v1/"
SANDBOXES_BASE_URL = "https://api.tokenfactory.nebius.com/sandboxes/v1"


def load_dotenv(path: Path | None = None) -> None:
    """Populate os.environ from a KEY=VALUE file without overriding variables already set."""
    path = path or Path(os.environ.get("LEAKPROOF_DOTENV", REPO_ROOT / ".env"))
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip().strip('"').strip("'")
        if value:
            os.environ.setdefault(key.strip(), value)


def require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} is not set; copy .env.example to .env and fill it in")
    return value


def budget_usd(default: float = 2.0) -> float:
    return float(os.environ.get("LEAKPROOF_BUDGET_USD", default))
