"""Evidence strength of a verified candidate (D-0074): how much the gate could actually observe.

"Verified" means no check failed. Two checks can only fail when the program gives them something
to compare, and some harnesses give them nothing:
  tests   the project's tests ran and passed (Juliet: the good-path build stayed clean)
  output  the differential corpus produced at least two distinct non-empty stdouts on the
          baseline, so a behaviour change could show up (Juliet, CUDA: the reproducer's output
          is compared, which counts)
strong = both, medium = one, weak = neither. A weak verified fix is labelled "verified, needs
human review": the verdict and the headline numbers stay, the label says where to look.
Pure functions over stored records; no gate imports.
"""

from __future__ import annotations

import re
from typing import Any

LEVELS = ("strong", "medium", "weak")
LABEL = {
    "strong": "verified",
    "medium": "verified",
    "weak": "verified, needs human review",
}
_RUNS = re.compile(r"runs=(\d+)")


def strength(checks: dict[str, Any], output_stats: dict[str, int] | None) -> dict[str, Any]:
    """Evidence of one gated candidate. `checks`: its gate checks ({name: {status, detail}});
    `output_stats`: the case's baseline corpus stats ({clean_inputs, stdout_distinct}) or None."""

    def status(name: str) -> str:
        return (checks.get(name) or {}).get("status", "absent")

    tests = status("tests") == "pass"
    if status("behavior") == "pass":
        output: bool | None = True
    elif output_stats is None:
        output = None
    else:
        output = output_stats.get("stdout_distinct", 0) >= 2
    m = _RUNS.search((checks.get("refuzz") or {}).get("detail", ""))
    level = LEVELS[2 - int(tests) - int(bool(output))]
    return {
        "level": level,
        "label": LABEL[level],
        "tests": tests,
        "output_varies": output,
        "stdout_distinct": (output_stats or {}).get("stdout_distinct"),
        "refuzz_runs": int(m.group(1)) if m else None,
        "safe_fix": status("safe_fix"),
    }


def explain(ev: dict[str, Any]) -> str:
    """One line for bundles, the CLI and the dashboard."""
    tests = "project tests ran" if ev["tests"] else "no project tests"
    if ev["output_varies"] is None:
        out = "harness output not measured"
    elif ev["output_varies"]:
        out = f"harness output varies ({ev['stdout_distinct'] or 'compared'})"
    else:
        out = "harness prints nothing the differential can compare"
    return f"evidence {ev['level']}: {tests}; {out}"
