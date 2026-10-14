"""Parsers against real reports generated in leakproof/cpp-sanitizers (tests/fixtures/src)."""

from __future__ import annotations

from pathlib import Path

import pytest

from leakproof.findings import parse_report, primary

FX = Path(__file__).parent / "fixtures"

# fixture -> (tool, kind, cwe, location, alloc_site, free_site)
EXPECTED = {
    "asan_leak.log": ("lsan", "leak", "CWE-401", "src/leak.c:3", "src/leak.c:3", None),
    "asan_cpp_leak.log": (
        "lsan",
        "leak",
        "CWE-401",
        "src/cpp_leak.cpp:3",
        "src/cpp_leak.cpp:3",
        None,
    ),
    "asan_heap_overflow.log": (
        "asan",
        "heap-buffer-overflow",
        "CWE-122",
        "src/heap_overflow.c:2",
        "src/heap_overflow.c:2",
        None,
    ),
    "asan_uaf.log": (
        "asan",
        "use-after-free",
        "CWE-416",
        "src/uaf.c:4",
        "src/uaf.c:4",
        "src/uaf.c:3",
    ),
    "asan_double_free.log": (
        "asan",
        "double-free",
        "CWE-415",
        "src/double_free.c:2",
        "src/double_free.c:2",
        "src/double_free.c:2",
    ),
    "asan_mismatch.log": (
        "asan",
        "alloc-dealloc-mismatch",
        "CWE-762",
        "src/mismatch.cpp:1",
        "src/mismatch.cpp:1",
        None,
    ),
    "asan_stack_overflow.log": (
        "asan",
        "stack-buffer-overflow",
        "CWE-121",
        "src/stack_overflow.c:2",
        None,
        None,
    ),
    "asan_segv.log": ("asan", "null-deref", "CWE-476", "src/null_deref.c:3", None, None),
    "asan_null_deref.log": ("ubsan", "null-deref", "CWE-476", "src/null_deref.c:3", None, None),
    "asan_ubsan_overflow.log": (
        "ubsan",
        "integer-overflow",
        "CWE-190",
        "src/ubsan_overflow.c:3",
        None,
        None,
    ),
}


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_fixture(name: str) -> None:
    findings = parse_report((FX / name).read_text())
    assert findings, f"nothing parsed from {name}"
    f = primary(findings)
    assert f is not None
    got = (f.tool, f.kind, f.cwe_guess, f.location, f.alloc_site, f.free_site)
    assert got == EXPECTED[name]
    assert f.frames and f.raw


def test_leak_details() -> None:
    (f,) = parse_report((FX / "asan_leak.log").read_text())
    assert f.leaked_bytes == 64 and f.leak_type == "direct"
    assert [fr.function for fr in f.frames[:3]] == ["malloc", "make", "main"]
    assert f.frames[0].is_runtime and not f.frames[1].is_runtime


def test_cpp_leak_direct_and_indirect() -> None:
    findings = parse_report((FX / "asan_cpp_leak.log").read_text())
    assert {f.leak_type for f in findings} == {"direct", "indirect"}


def test_access_fields() -> None:
    f = primary(parse_report((FX / "asan_heap_overflow.log").read_text()))
    assert f is not None and (f.access, f.access_size) == ("WRITE", 4)
    (f,) = parse_report((FX / "asan_segv.log").read_text())
    assert f.access == "READ"


def test_valgrind_leak() -> None:
    findings = parse_report((FX / "valgrind_leak.log").read_text())
    assert [(f.tool, f.kind, f.leaked_bytes, f.alloc_site) for f in findings] == [
        ("valgrind", "leak", 64, "src/leak.c:3")
    ]


def test_to_dict_has_sites() -> None:
    (f,) = parse_report((FX / "asan_uaf.log").read_text())
    d = f.to_dict(include_raw=False)
    assert d["free_site"] == "src/uaf.c:3" and "raw" not in d


def test_empty_and_clean_output() -> None:
    assert parse_report("") == []
    assert parse_report("all good\n") == []


def test_ubsan_object_size_alone_and_with_asan() -> None:
    (f,) = parse_report((FX / "ubsan_object_size.log").read_text())
    assert (f.tool, f.kind, f.cwe_guess) == ("ubsan", "object-size-overflow", "CWE-787")
    both = parse_report((FX / "asan_heap_overflow.log").read_text())
    assert [x.tool for x in both] == ["ubsan", "asan"]
