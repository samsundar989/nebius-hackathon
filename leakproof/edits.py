"""Search/replace edit blocks (D-0026): the worker's output format.

    path/to/file.c
    <<<<<<< SEARCH
    exact lines from the file
    =======
    replacement lines
    >>>>>>> REPLACE

A SEARCH block must match exactly once: first verbatim, then line-by-line ignoring whitespace.
We write the unified diff ourselves, so the model never has to get diff syntax right.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass

# Lenient on marker length and a missing "REPLACE": models drift on both.
SEARCH = re.compile(r"^<{5,}\s*SEARCH\s*$")
DIVIDER = re.compile(r"^={5,}\s*$")
REPLACE = re.compile(r"^>{5,}\s*(REPLACE)?\s*$")


class EditError(ValueError):
    pass


@dataclass
class EditBlock:
    path: str
    search: str
    replace: str


def _clean_path(line: str) -> str:
    return line.strip().strip("`*#:").strip()


def parse_blocks(text: str) -> list[EditBlock]:
    """Every SEARCH/REPLACE block in `text`; the path is the nearest non-fence line above it."""
    lines = text.splitlines()
    blocks: list[EditBlock] = []
    path = ""
    i = 0
    while i < len(lines):
        line = lines[i]
        if SEARCH.match(line.strip()):
            j = i - 1
            while j >= 0 and (not lines[j].strip() or lines[j].strip().startswith("```")):
                j -= 1
            candidate = _clean_path(lines[j]) if j >= 0 else ""
            if candidate and re.fullmatch(r"[\w./+-]+", candidate):
                path = candidate
            try:
                mid = next(k for k in range(i + 1, len(lines)) if DIVIDER.match(lines[k].strip()))
                end = next(k for k in range(mid + 1, len(lines)) if REPLACE.match(lines[k].strip()))
            except StopIteration as exc:
                raise EditError("unterminated SEARCH/REPLACE block") from exc
            if not path:
                raise EditError("SEARCH block without a file path line above it")
            blocks.append(
                EditBlock(path, "\n".join(lines[i + 1 : mid]), "\n".join(lines[mid + 1 : end]))
            )
            i = end + 1
            continue
        i += 1
    return blocks


def _norm(line: str) -> str:
    return " ".join(line.split())


def apply_block(source: str, block: EditBlock) -> tuple[str, str]:
    """Return (new source, strategy) or raise EditError naming the mismatch."""
    if not block.search.strip():
        raise EditError(f"{block.path}: empty SEARCH (insertions need an anchor line)")
    count = source.count(block.search)
    if count == 1:
        return source.replace(block.search, block.replace, 1), "exact"
    if count > 1:
        raise EditError(f"{block.path}: SEARCH matches {count} times; add context lines")
    lines = source.splitlines()
    needle = [_norm(x) for x in block.search.splitlines()]
    while needle and not needle[0]:
        needle.pop(0)
    while needle and not needle[-1]:
        needle.pop()
    hay = [_norm(x) for x in lines]
    hits = _hits(hay, needle)
    how = "whitespace"
    if len(hits) == 1:
        i, end = hits[0], hits[0] + len(needle)
    elif not hits:
        # Models drop comment-only and blank lines when quoting; match on code lines alone.
        code_idx = [k for k, h in enumerate(hay) if h and not _COMMENT.match(h)]
        code_needle = [n for n in needle if n and not _COMMENT.match(n)]
        code_hits = _hits([hay[k] for k in code_idx], code_needle) if code_needle else []
        if len(code_hits) != 1:
            raise EditError(
                f"{block.path}: SEARCH matches 0 times (even ignoring whitespace and comment "
                f"lines); first SEARCH line was: {block.search.strip().splitlines()[0]!r}"
            )
        j = code_hits[0]
        i, end, how = code_idx[j], code_idx[j + len(code_needle) - 1] + 1, "code_lines"
    else:
        raise EditError(
            f"{block.path}: SEARCH matches {len(hits)} times (whitespace-insensitive); "
            "add context lines"
        )
    # Models often shift a whole block's indentation; move the replacement by the same offset
    # the SEARCH text was off by, so the diff shows only the real change.
    have = _indent(lines[i])
    said = _indent(next(x for x in block.search.splitlines() if x.strip()))
    replacement = [
        have + x[len(said) :] if x.startswith(said) else x for x in block.replace.splitlines()
    ]
    lines[i:end] = replacement
    return "\n".join(lines) + ("\n" if source.endswith("\n") else ""), how


_COMMENT = re.compile(r"^(//.*|/\*.*\*/)$")


def _hits(hay: list[str], needle: list[str]) -> list[int]:
    return [i for i in range(len(hay) - len(needle) + 1) if hay[i : i + len(needle)] == needle]


def _indent(line: str) -> str:
    return line[: len(line) - len(line.lstrip())]


def apply_blocks(
    files: dict[str, str], blocks: list[EditBlock]
) -> tuple[dict[str, str], list[str]]:
    """Apply blocks to {path: source}; unknown paths are an error (scope is the caller's list).

    With a single file in scope every block targets it, whatever path the model wrote."""
    out = dict(files)
    strategies = []
    for block in blocks:
        if block.path not in out:
            # Models add or drop leading directories ("src/x.c" for "x.c"): suffix, then basename.
            matches = [p for p in out if p.endswith("/" + block.path.lstrip("/"))]
            if not matches:
                base = block.path.rsplit("/", 1)[-1]
                matches = [p for p in out if p.rsplit("/", 1)[-1] == base]
            if len(out) == 1:
                matches = list(out)
            if len(matches) != 1:
                raise EditError(f"{block.path}: not one of the files you were given")
            block = EditBlock(matches[0], block.search, block.replace)
        out[block.path], how = apply_block(out[block.path], block)
        strategies.append(how)
    return out, strategies


def unified_diff(before: dict[str, str], after: dict[str, str]) -> str:
    chunks = []
    for path in sorted(after):
        if before.get(path) == after[path]:
            continue
        chunks.extend(
            difflib.unified_diff(
                before.get(path, "").splitlines(keepends=True),
                after[path].splitlines(keepends=True),
                fromfile=f"a/{path.lstrip('/')}",
                tofile=f"b/{path.lstrip('/')}",
            )
        )
    return "".join(c if c.endswith("\n") else c + "\n" for c in chunks)
