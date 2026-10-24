"""Case suites behind one interface (base.Case): Juliet (synthetic) and ARVO (real OSS-Fuzz)."""

from leakproof.cases.arvo import ArvoCase
from leakproof.cases.base import BuildResult, Case, Window
from leakproof.cases.juliet import JulietCase

__all__ = ["ArvoCase", "BuildResult", "Case", "JulietCase", "Window", "load_case"]


def load_case(case_id: str) -> Case:
    """`project:<leakproof.toml>` is a bring-your-own project; numeric ids are ARVO localIds;
    everything else is a Juliet case id."""
    if case_id.startswith("project:"):
        from leakproof.cases.project import ProjectCase

        return ProjectCase.load(case_id)
    return ArvoCase.load(case_id) if case_id.isdigit() else JulietCase.load(case_id)
