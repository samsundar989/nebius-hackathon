"""The ledger survives concurrent appends from several processes (D-0054)."""

import json
import subprocess
import sys
from pathlib import Path

WRITER = """
import sys
from pathlib import Path
from leakproof.llm.ledger import CostLedger, LedgerEntry
led = CostLedger(path=Path(sys.argv[1]), budget=1e9)
for i in range(150):
    led.record(LedgerEntry("m", "p", f"w{sys.argv[2]}", 1, 1, 0, 0.001, 0.0, note="x" * 300))
    if i % 25 == 0:
        led.file_total()
"""


def test_parallel_processes_never_corrupt_lines(tmp_path: Path) -> None:
    path = tmp_path / "ledger.jsonl"
    procs = [subprocess.Popen([sys.executable, "-c", WRITER, str(path), str(k)]) for k in range(4)]
    assert all(p.wait(timeout=120) == 0 for p in procs)
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 600
    assert all(json.loads(line)["usd"] == 0.001 for line in lines)


def test_bad_line_is_counted_not_fatal(tmp_path: Path, capsys) -> None:  # noqa: ANN001
    from leakproof.llm.ledger import CostLedger

    path = tmp_path / "ledger.jsonl"
    path.write_text('{"usd": 0.5}\nMITGOOD -Isupport -", "ts": 1}\n{"usd": 0.25}\n')
    assert CostLedger(path=path, budget=1).file_total() == 0.75
    assert "1 unparsable" in capsys.readouterr().err
