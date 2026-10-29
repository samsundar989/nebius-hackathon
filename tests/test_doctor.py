"""`leakproof doctor` config checks (no Docker, no network)."""

from pathlib import Path

from leakproof.doctor import check_config


def test_missing_fields_fail_with_the_names(tmp_path: Path) -> None:
    p = tmp_path / "leakproof.toml"
    p.write_text('[project]\nname = "x"\n')
    (status, name, detail, _fix), *_ = check_config(p)
    assert status == "FAIL" and "build" in detail and "reproduce" in detail


def test_unknown_keys_warn(tmp_path: Path) -> None:
    p = tmp_path / "leakproof.toml"
    p.write_text('[project]\nname = "x"\nbuild = "make"\nreproduce = "./x"\nreproducer = "y"\n')
    rows = check_config(p)
    assert rows[0][0] == "PASS"
    assert any(r[0] == "WARN" and "reproducer" in r[2] for r in rows)


def test_bad_toml_fails(tmp_path: Path) -> None:
    p = tmp_path / "leakproof.toml"
    p.write_text("[project\n")
    assert check_config(p)[0][0] == "FAIL"
