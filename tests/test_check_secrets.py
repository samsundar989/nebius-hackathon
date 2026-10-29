from pathlib import Path

import check_secrets

FAKE = "x" * 10 + "AbCdEf0123456789"


def _scan(tmp_path: Path, name: str, text: str) -> list[str]:
    p = tmp_path / name
    p.write_text(text)
    return check_secrets.scan([p])


def test_flags_env_assignment(tmp_path: Path) -> None:
    assert _scan(tmp_path, "a.py", f"NEBIUS_API_KEY={FAKE}\n")


def test_flags_long_token(tmp_path: Path) -> None:
    assert _scan(tmp_path, "a.txt", "token: " + "Ab9_" * 40 + "\n")


def test_flags_env_file_by_name(tmp_path: Path) -> None:
    assert _scan(tmp_path, ".env", "nothing\n")


def test_allows_names_without_values(tmp_path: Path) -> None:
    assert not _scan(
        tmp_path, "a.md", "Set NEBIUS_API_KEY= in .env\nos.environ['NEBIUS_API_KEY']\n"
    )


def test_allow_marker(tmp_path: Path) -> None:
    assert not _scan(tmp_path, "a.py", f"NEBIUS_API_KEY={FAKE}  # secret-scan: allow\n")


def test_padding_runs_are_not_secrets(tmp_path: Path) -> None:
    scan = check_secrets.scan
    f = tmp_path / "poc.gltf"
    f.write_text('{"uri":"data:' + "A" * 133 + ',X"}')
    assert scan([f]) == []
    g = tmp_path / "leak.txt"
    g.write_text("k=" + "aB3dE5" * 25)
    assert scan([g])
