"""Triage clustering (D-0064): one signature per root cause, lines ignored, runtime frames ignored."""

from leakproof.triage import cluster


def _report(kind: str, line: int, fn: str = "copy_quoted") -> str:
    return (
        f"==1==ERROR: AddressSanitizer: {kind} on address 0x602 at pc 0x1 bp 0x2 sp 0x3\n"
        "WRITE of size 1 at 0x602 thread T0\n"
        "    #0 0x1 in __asan_memcpy /src/llvm-project/compiler-rt/lib/asan/asan_interceptors.cpp:22\n"
        f"    #1 0x2 in {fn} /src/csvsplit/src/csvsplit.c:{line}:5\n"
        "    #2 0x3 in csv_split /src/csvsplit/src/csvsplit.c:55:21\n"
    )


def test_same_bug_at_shifted_lines_is_one_cluster() -> None:
    reports = {
        "a": _report("heap-buffer-overflow", 33),
        "bb": _report("heap-buffer-overflow", 35),
        "c": _report("heap-use-after-free", 33, "csv_free"),
        "ok": "INFO: Running\nExecuted ok in 1 ms\n",
    }
    clusters, clean = cluster(reports, {"a": 9, "bb": 4, "c": 5, "ok": 1}, "/src/csvsplit/")
    assert clean == ["ok"] and len(clusters) == 2
    big = clusters[0]
    assert big.members == ["a", "bb"] and big.representative == "bb"  # smallest input
    assert big.signature == (
        "heap-buffer-overflow",
        "copy_quoted csvsplit.c",
        "csv_split csvsplit.c",
    )
