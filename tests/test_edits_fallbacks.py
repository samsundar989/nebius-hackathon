"""Edit robustness (D-0058): terminators models actually write, line ranges, whole functions."""

import pytest

from leakproof.edits import EditError, apply_blocks, parse_blocks

SRC = """static int helper(int x)
{
    return x + 1;
}

static void
parse(char *buf, int n)
{
    int i;
    for (i = 0; i <= n; i++) {
        buf[i] = 0;
    }
}
"""
FILES = {"/src/p/a.c": SRC}


def test_second_divider_closes_a_block() -> None:
    # c-ares 42482401 (P3): complete edits closed with "=======" instead of ">>>>>>> REPLACE".
    text = "a.c\n<<<<<<< SEARCH\n    for (i = 0; i <= n; i++) {\n=======\n    for (i = 0; i < n; i++) {\n=======\n"
    blocks = parse_blocks(text)
    out, how = apply_blocks(FILES, blocks)
    assert "i < n" in out["/src/p/a.c"] and how == ["exact"]


def test_truncated_reply_is_still_an_error_but_complete_reply_may_end_at_eof() -> None:
    text = "a.c\n<<<<<<< SEARCH\n    for (i = 0; i <= n; i++) {\n=======\n    for (i = 0; i < n; i++) {"
    with pytest.raises(EditError, match="unterminated"):
        parse_blocks(text)
    assert parse_blocks(text, complete=True)[0].replace.strip().startswith("for (i = 0; i < n")


def test_line_numbers_copied_into_search_are_stripped() -> None:
    text = "a.c\n<<<<<<< SEARCH\n   10|     for (i = 0; i <= n; i++) {\n=======\n   10|     for (i = 0; i < n; i++) {\n>>>>>>> REPLACE\n"
    out, _ = apply_blocks(FILES, parse_blocks(text))
    assert "i < n" in out["/src/p/a.c"] and "10|" not in out["/src/p/a.c"]


def test_line_range_replaces_shown_lines_only() -> None:
    text = "@@ replace a.c lines 10-10 @@\n    for (i = 0; i < n; i++) {\n@@ end @@\n"
    blocks = parse_blocks(text)
    out, how = apply_blocks(FILES, blocks, {"/src/p/a.c": [(6, 13)]})
    assert out["/src/p/a.c"].splitlines()[9].strip() == "for (i = 0; i < n; i++) {"
    assert how == ["line_range"]
    with pytest.raises(EditError, match="not inside one window"):
        apply_blocks(FILES, parse_blocks(text), {"/src/p/a.c": [(1, 4)]})


def test_function_replacement_by_name_with_return_type_line() -> None:
    new = "static void\nparse(char *buf, int n)\n{\n    memset(buf, 0, (size_t)n);\n}"
    text = f"@@ function parse in a.c @@\n{new}\n@@ end @@\n"
    out, how = apply_blocks(FILES, parse_blocks(text))
    src = out["/src/p/a.c"]
    assert "memset" in src and "i <= n" not in src and src.count("static void") == 1
    assert "return x + 1" in src and how == ["function"]


def test_function_not_found_is_an_error() -> None:
    with pytest.raises(EditError, match="no definition"):
        apply_blocks(FILES, parse_blocks("@@ function nope in a.c @@\nx\n@@ end @@\n"))
