from pathlib import Path

from leakproof import init


def _repo(tmp_path: Path, files: dict[str, str]) -> Path:
    for name, text in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    return tmp_path


def test_detect_order_and_tests(tmp_path: Path) -> None:
    repo = _repo(
        tmp_path,
        {"Makefile": "all:\n\tcc x.c\ncheck: all\n", "CMakeLists.txt": "add_test(x x)\n"},
    )
    d = init.detect(repo)
    assert d["system"] == "make" and d["test"] == "make check"
    assert 'CC="clang $CFLAGS"' in d["build"]  # flags survive a Makefile's own CFLAGS


def test_hand_written_configure_is_not_autotools(tmp_path: Path) -> None:
    repo = _repo(tmp_path, {"configure": "#!/bin/sh\necho hi\n", "Makefile": "defconfig:\n"})
    d = init.detect(repo)
    assert d["system"] == "make" and "make defconfig" in d["build"]


def test_cmake_ctest(tmp_path: Path) -> None:
    d = init.detect(_repo(tmp_path, {"CMakeLists.txt": "enable_testing()\n"}))
    assert d["system"] == "cmake" and d["test"].startswith("ctest")


def test_editable_skips_tests(tmp_path: Path) -> None:
    repo = _repo(tmp_path, {"src/a.c": "", "src/b.c": "", "tests/t.c": "", "src/a.h": ""})
    assert init.editable(repo) == ["src/*.c", "src/*.h"]


def test_reproduce_replaces_reporter_file() -> None:
    issue = {"program": "./berry", "args": "poc.be", "input_kind": "file"}
    assert init.reproduce_cmd(issue) == "./berry /tmp/poc"
    issue = {"program": "fuzzer", "args": "-runs=0 crash.bin", "input_kind": "file"}
    assert init.reproduce_cmd(issue) == "./fuzzer -runs=0 /tmp/poc"
    assert init.reproduce_cmd({"program": "t", "args": "x", "input_kind": "stdin"}) == (
        "./t x < /tmp/poc"
    )


def test_poc_bytes_decodings() -> None:
    hex_issue = {
        "input_kind": "file",
        "input_text": "0x07 0xe8 \\x00",
        "input_encoding": "hex_bytes",
    }
    assert init.poc_bytes(hex_issue) == b"\x07\xe8\x00"
    esc = {"input_kind": "file", "input_text": 'a\\nb\\"', "input_encoding": "text"}
    assert init.poc_bytes(esc) == b'a\nb"\n'
    plain = {"input_kind": "stdin", "input_text": "x", "input_encoding": "text"}
    assert init.poc_bytes(plain) == b"x\n"
    assert init.poc_bytes({"input_kind": "none", "input_text": "x"}) is None
