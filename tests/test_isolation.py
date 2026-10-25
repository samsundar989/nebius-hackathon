"""Workers never see the gate (CLAUDE.md rule 7): the worker path imports no gate-side module."""

import ast
from pathlib import Path

PKG = Path(__file__).resolve().parent.parent / "leakproof"
WORKER_PATH = [
    "planner.py",
    "worker.py",
    "branch.py",
    "context.py",
    "edits.py",
    "fix.py",
    "feedback.py",
    "audit.py",
    "winner.py",
]
GATE_SIDE = {"leakproof.gate", "leakproof.gate_fuzz", "leakproof.calibrate", "leakproof.semantic"}


def _imports(path: Path) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
            names |= {f"{node.module}.{a.name}" for a in node.names}
    return names


def test_worker_path_imports_no_gate_module() -> None:
    for name in WORKER_PATH:
        hits = _imports(PKG / name) & GATE_SIDE
        assert not hits, f"{name} imports {hits}"
