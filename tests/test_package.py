from pathlib import Path

from leakproof import package as pk

FINDING = {
    "kind": "heap-buffer-overflow",
    "location": "/src/demo/src/a.c:33",
    "frames": [
        {"function": "malloc", "file": "/src/llvm-project/asan.cpp"},
        {"function": "copy", "file": "/src/demo/src/a.c"},
    ],
}
DIFF = (
    "--- a/src/demo/src/a.c\n+++ b/src/demo/src/a.c\n@@ -1,2 +1,2 @@\n"
    " int x;\n-char *f = malloc(n);\n+char *f = malloc(n + 1);\n"
)


def test_repo_diff_strips_the_container_prefix() -> None:
    d = pk.repo_diff(DIFF)
    assert d.startswith("diff --git a/src/a.c b/src/a.c\n--- a/src/a.c\n+++ b/src/a.c")
    assert "1 file(s) changed, 1 insertion(s)(+), 1 deletion(s)(-)" in pk.diffstat(d)


def test_commit_message_from_finding_and_root_cause() -> None:
    msg = pk.commit_message(FINDING, "One. Two sentences here. " + "Long. " * 80, "572")
    subject, _, body = msg.partition("\n\n")
    assert subject == "a: fix heap-buffer-overflow in copy()"
    assert body.startswith("One. Two sentences here.")
    assert "AddressSanitizer: heap-buffer-overflow at src/a.c:33." in body
    assert msg.endswith("Fixes #572.")
    assert all(len(line) <= 72 for line in body.splitlines())


def test_evidence_rows_cover_checks_that_did_not_run() -> None:
    rows = pk.evidence_rows({"patched": {"status": "pass", "detail": "clean"}})
    results = {w: r for w, r, _ in rows}
    assert results["the reproducer runs clean under the sanitizers"] == "pass"
    assert results["the project's own tests pass"] == "not run"
    assert results["inputs a Nemotron model wrote to break this patch"] == "not run"


def test_package_writes_both_files_with_banner(tmp_path: Path) -> None:
    checks = {
        "patched": {"status": "pass", "detail": "clean"},
        "tests": {"status": "skipped", "detail": "no tests"},
        "refuzz": {"status": "skipped", "detail": "no fuzz harness"},
    }
    sp, pp = pk.package(
        out=tmp_path,
        finding=FINDING,
        root_cause="The buffer has no room for the terminator.",
        diff=DIFF,
        checks=checks,
        verdict="verified",
        source="runs/x.json",
        title="demo",
    )
    text = sp.read_text(encoding="utf-8")
    assert "Verified, needs human review" in text and "## Before sending" in text
    patch = pp.read_text(encoding="utf-8")
    assert patch.startswith("From 0000000000000000000000000000000000000000")
    assert "From: <your git identity>" in patch and "diff --git a/src/a.c" in patch
