"""Case suites behind one interface (base.Case): Juliet (synthetic) and ARVO (real OSS-Fuzz)."""

from leakproof.cases.arvo import ArvoCase
from leakproof.cases.base import BuildResult, Case, Window
from leakproof.cases.juliet import JulietCase

__all__ = ["ArvoCase", "BuildResult", "Case", "JulietCase", "Window", "load_case"]


def load_case(case_id: str) -> Case:
    """Numeric ids are ARVO localIds; everything else is a Juliet case id."""
    return ArvoCase.load(case_id) if case_id.isdigit() else JulietCase.load(case_id)
