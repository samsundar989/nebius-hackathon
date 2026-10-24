"""Bring-your-own project adapter (leakproof.toml) without Docker."""

from pathlib import Path

import pytest

from leakproof.cases import load_case
from leakproof.cases.project import ProjectCase
from leakproof.fix import case_slug

DEMO = Path(__file__).resolve().parent.parent / "examples" / "csvsplit" / "leakproof.toml"


def test_demo_config_loads_with_gate_hooks() -> None:
    case = load_case(f"project:{DEMO}")
    assert isinstance(case, ProjectCase) and case.suite == "project"
    assert case.workdir == "/src/csvsplit" and case.src_root == "/src/csvsplit/"
    assert case.harness_path == "/src/csvsplit/csvsplit_fuzz" == case.artifact_path
    assert case.reproduce_cmd == "./csvsplit_fuzz /tmp/poc" and case.tests_cmd == "make test"
    assert "-fsanitize=address" in case.build_env["CFLAGS"]
    assert case.gate_build_cmd({"/src/csvsplit/src/csvsplit.c": "x"}).startswith("touch ")


def test_editable_follows_globs_and_never_the_harness_or_tests() -> None:
    case = ProjectCase.load(f"project:{DEMO}")
    assert case._editable("/src/csvsplit/src/csvsplit.c")
    assert not case._editable("/src/csvsplit/fuzz/csvsplit_fuzz.c")
    assert not case._editable("/src/csvsplit/tests/test_csvsplit.c")
    assert not case._editable("/src/csvsplit/Makefile")


def test_tree_copies_sources_and_corpus_not_build_dirs(tmp_path: Path) -> None:
    case = ProjectCase.load(f"project:{DEMO}")
    tree = case._tree()
    assert "/src/csvsplit/src/csvsplit.c" in tree and "/src/csvsplit/corpus/plain1" in tree
    assert not any("/.git/" in k for k in tree)


def test_missing_required_key_is_an_error(tmp_path: Path) -> None:
    cfg = tmp_path / "leakproof.toml"
    cfg.write_text('[project]\nname = "x"\nbuild = "make"\n')
    with pytest.raises(ValueError, match="reproduce"):
        ProjectCase.load(f"project:{cfg}")


def test_case_slug_is_a_valid_file_name() -> None:
    assert case_slug(f"project:{DEMO}") == "project_csvsplit"
    assert case_slug("42530604") == "42530604"
