#!/usr/bin/env python3
"""Re-gate every distinct verified open-bugs diff under the harness-less checks (D-0078).

scripts/regate_open_bugs.py ROOT   -> runs/open_bugs_regate/<case>/gate.json (no model calls)

ROOT is the live checkout (the upstream clones are not in workerq's snapshot). cNBT has a fuzz
harness, so its verdicts already came from the harness path and it is not re-gated here.
Needs Docker: submit through workerq (scripts/lp_job.ps1).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# case dir -> (config, [(id, source)]) ; source: "patch:<file>" or "<record>:<HYP>:<worker>"
CASES = {
    "berry_544_format": (
        "cases/open_bugs/berry-lang_berry/544_format/leakproof.toml",
        [
            ("H1w0", "runs/open_bugs_fix/project_544_format.json:H1:0"),
            ("H3w2", "runs/open_bugs_fix/project_544_format.json:H3:2"),
            ("H4w3", "runs/open_bugs_fix/project_544_format.json:H4:3"),
        ],
    ),
    "toybox_571": (
        "cases/open_bugs/landley_toybox/571/leakproof.toml",
        [("H2w1", "runs/open_bugs_fix2/project_571.json:H2:1")],
    ),
    "toybox_572": (
        "cases/open_bugs/landley_toybox/572/leakproof.toml",
        [
            ("M1", "patch:cases/open_bugs/landley_toybox/572/one_line.diff"),
            ("H2w1", "runs/open_bugs_fix2/project_572.json:H2:1"),
            ("H3w2", "runs/open_bugs_fix2/project_572.json:H3:2"),
            ("H1w0", "runs/open_bugs_fix2/project_572.json:H1:0"),
        ],
    ),
    "jsmn_249": (
        "cases/open_bugs/zserge_jsmn/leakproof.toml",
        [("H2w3", "runs/open_bugs_r2/project_zserge_jsmn.json:H2:3")],
    ),
}


def main() -> int:
    root = Path(sys.argv[1]).resolve()
    only = set(sys.argv[2].split(",")) if len(sys.argv) > 2 else None
    for case, (config, cands) in CASES.items():
        if only and case not in only:
            continue
        cmd = [
            sys.executable,
            str(Path(__file__).with_name("gate_manual.py")),
            "--config",
            str(root / config),
            "--out",
            str(root / "runs" / "open_bugs_regate" / case),
        ]
        for cid, src in cands:
            if src.startswith("patch:"):
                cmd += ["--patch", f"{cid}={root / src.removeprefix('patch:')}"]
            else:
                rec, hyp, idx = src.rsplit(":", 2)
                cmd += ["--from-record", f"{cid}={root / rec}:{hyp}:{idx}"]
        print("==", case, flush=True)
        subprocess.run(cmd, check=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
