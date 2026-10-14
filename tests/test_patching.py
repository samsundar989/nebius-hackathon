import pytest

from leakproof.patching import PatchError, apply_hunks, parse_diff

SRC = "int f(void)\n{\n    char *p = g();\n    use(p);\n    /* no free */\n    ; /* empty */\n}\n"


def test_exact_apply_ignores_wrong_header() -> None:
    diff = "--- a/x.c\n+++ b/x.c\n@@ -90,3 +90,3 @@\n     use(p);\n-    /* no free */\n+    free(p);\n     ; /* empty */\n"
    out, used = apply_hunks(SRC, parse_diff(diff)["x.c"])
    assert "    free(p);\n" in out and "no free" not in out and used == ["exact"]


def test_misquoted_context_falls_back_to_removed_lines() -> None:
    # Context line misquoted (dropped ';'), as Lightning produced in E0.
    diff = "--- a/x.c\n+++ b/x.c\n@@ -1,3 +1,3 @@\n     use(p);\n-    /* no free */\n+    free(p);\n     /* empty */\n #endif\n"
    out, used = apply_hunks(SRC, parse_diff(diff)["x.c"])
    assert "free(p);" in out and used == ["removed-lines"]
    assert out.count("\n") == SRC.count("\n")


def test_ambiguous_fails() -> None:
    src = "a\nx\nb\nx\n"
    diff = "--- a/f\n+++ b/f\n@@ -1 +1 @@\n zz\n-x\n+y\n"
    with pytest.raises(PatchError):
        apply_hunks(src, parse_diff(diff)["f"])


def test_empty_diff_rejected() -> None:
    with pytest.raises(PatchError):
        parse_diff("")
