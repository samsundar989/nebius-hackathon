"""Search/replace edit blocks (D-0026): the worker's output format.

    path/to/file.c
    <<<<<<< SEARCH
    exact lines from the file
    =======
    replacement lines
    >>>>>>> REPLACE

A SEARCH block must match exactly once: first verbatim, then line-by-line ignoring whitespace.
We write the unified diff ourselves, so the model never has to get diff syntax right.

Fallbacks (D-0058), for when SEARCH text will not match what the model remembers:

    @@ replace path/to/file.c lines 120-134 @@      the shown lines 120-134, replaced
    <new lines>
    @@ end @@

    @@ function name in path/to/file.c @@           the whole definition of `name`, replaced
    <the complete new function>
    @@ end @@

A line range applies only inside a window the worker was shown (the lines it saw are the lines
it replaces); a function is located by name and brace matching.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass

# Lenient on marker length and a missing "REPLACE": models drift on both.
SEARCH = re.compile(r"^<{5,}\s*SEARCH\s*$")
DIVIDER = re.compile(r"^={5,}\s*$")
REPLACE = re.compile(r"^>{5,}\s*(REPLACE)?\s*$")
SOURCE_PATH = re.compile(r"[\w./+-]+\.(c|h|cc|cpp|cxx|hpp|hh|inc|inl)\b")
RANGE = re.compile(r"^@@\s*replace\s+`?([\w./+-]+)`?\s+lines?\s+(\d+)\s*-\s*(\d+)\s*@@$", re.I)
FUNCTION = re.compile(r"^@@\s*function\s+`?(\w+)`?\s+in\s+`?([\w./+-]+)`?\s*@@$", re.I)
END = re.compile(r"^@@\s*end\s*@@$", re.I)
# Windows are shown with line numbers ("  120| code"); models sometimes copy the prefix.
NUMBERED = re.compile(r"^\s*\d+\|\s?")


class EditError(ValueError):
    pass


@dataclass
class EditBlock:
    path: str
    search: str
    replace: str
    kind: str = "search"  # search | range | function
    start: int = 0  # range: 1-based inclusive
    end: int = 0
    name: str = ""  # function


def _unnumber(text: str) -> str:
    lines = text.splitlines()
    if lines and all(NUMBERED.match(x) for x in lines if x.strip()):
        return "\n".join(NUMBERED.sub("", x, count=1) for x in lines)
    return text


def _clean_path(line: str) -> str:
    return line.strip().strip("`*#:").strip()


def parse_blocks(text: str, complete: bool = False) -> list[EditBlock]:
    """Every edit block in `text` (SEARCH/REPLACE, line range, function); for SEARCH blocks the
    path is the nearest non-fence line above. `complete`: the reply was not cut off, so a last
    block may end at the end of the text."""
    lines = text.splitlines()
    blocks: list[EditBlock] = []
    path = ""
    i = 0
    while i < len(lines):
        line = lines[i]
        header = RANGE.match(line.strip()) or FUNCTION.match(line.strip())
        if header:
            end = next((k for k in range(i + 1, len(lines)) if END.match(lines[k].strip())), None)
            if end is None:
                fence = next(
                    (k for k in range(i + 1, len(lines)) if lines[k].strip().startswith("```")),
                    None,
                )
                if fence is None and not complete:
                    raise EditError("unterminated @@ block (missing '@@ end @@')")
                end = fence if fence is not None else len(lines)
            body = "\n".join(x for x in lines[i + 1 : end] if not x.strip().startswith("```"))
            body = _unnumber(body)
            if header.re is RANGE:
                p, a, b = header.group(1), int(header.group(2)), int(header.group(3))
                blocks.append(EditBlock(p, "", body, "range", min(a, b), max(a, b)))
            else:
                blocks.append(
                    EditBlock(header.group(2), "", body, "function", name=header.group(1))
                )
            i = end + 1
            continue
        if SEARCH.match(line.strip()):
            j = i - 1
            while j >= 0 and (not lines[j].strip() or lines[j].strip().startswith("```")):
                j -= 1
            candidate = _clean_path(lines[j]) if j >= 0 else ""
            if candidate and re.fullmatch(r"[\w./+-]+", candidate):
                path = candidate
            elif m := SOURCE_PATH.search(candidate):  # "Edit: /src/x/conf.c", "File `a.c`:"
                path = m.group(0)
            try:
                mid = next(k for k in range(i + 1, len(lines)) if DIVIDER.match(lines[k].strip()))
            except StopIteration as exc:
                raise EditError("unterminated SEARCH/REPLACE block") from exc
            # The closing marker: ">>>>>>> REPLACE", or what models also write instead - a
            # second "=======" (P3: 10 complete edits lost to it), a fence, or the next block.
            end = next(
                (
                    k
                    for k in range(mid + 1, len(lines))
                    if REPLACE.match(lines[k].strip())
                    or DIVIDER.match(lines[k].strip())
                    or SEARCH.match(lines[k].strip())
                    or lines[k].strip().startswith("```")
                ),
                None,
            )
            if end is None:
                if not complete:
                    raise EditError("unterminated SEARCH/REPLACE block")
                end = len(lines)
            if not path:
                raise EditError("SEARCH block without a file path line above it")
            blocks.append(
                EditBlock(
                    path,
                    _unnumber("\n".join(lines[i + 1 : mid])),
                    _unnumber("\n".join(lines[mid + 1 : end])),
                )
            )
            if end < len(lines) and SEARCH.match(lines[end].strip()):
                i = end  # the next block starts right here (same file unless it names one)
                continue
            i = end + 1
            continue
        i += 1
    return blocks


_HUNK_LINE = re.compile(r"^[ +-]")
_DIFF_PATH = re.compile(r"^(?:\+\+\+ b/|--- a/|===\s*|diff --git a/\S+ b/)(\S+?\.\w+)\b")


def parse_unified(text: str) -> list[EditBlock]:
    """Diff-shaped replies (`-`/`+`/` ` lines, P3 r2: 'no edit blocks' for 11 workers that wrote
    one) as SEARCH/REPLACE blocks: context + `-` lines are SEARCH, context + `+` lines REPLACE."""
    blocks: list[EditBlock] = []
    path, hunk = "", []

    def flush() -> None:
        while hunk and hunk[-1] == " ":
            hunk.pop()
        if any(x[:1] in "+-" for x in hunk):
            old = "\n".join(x[1:] for x in hunk if x[:1] in " -")
            new = "\n".join(x[1:] for x in hunk if x[:1] in " +")
            if old.strip() and old != new:
                blocks.append(EditBlock(path or "?", old, new))
        hunk.clear()

    for line in text.splitlines():
        m = _DIFF_PATH.match(line.strip())
        if m:
            flush()
            path = m.group(1)
        elif line.startswith(("+++", "---")):
            continue
        elif line == "" and hunk:
            hunk.append(" ")  # a blank context line whose leading space was stripped
        elif line.startswith("@@") or line.strip().startswith("```") or not _HUNK_LINE.match(line):
            flush()
        else:
            hunk.append(line)
    flush()
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


def apply_range(source: str, block: EditBlock, shown: list[tuple[int, int]] | None) -> str:
    lines = source.splitlines()
    a, b = block.start, block.end
    if not 1 <= a <= b <= len(lines):
        raise EditError(f"{block.path}: lines {a}-{b} are outside the file (1-{len(lines)})")
    if shown is not None and not any(lo <= a and b <= hi for lo, hi in shown):
        raise EditError(
            f"{block.path}: lines {a}-{b} are not inside one window you were shown "
            f"({', '.join(f'{lo}-{hi}' for lo, hi in shown) or 'none'})"
        )
    _same_braces(block, "\n".join(lines[a - 1 : b]), block.replace)
    lines[a - 1 : b] = block.replace.splitlines()
    return "\n".join(lines) + ("\n" if source.endswith("\n") else "")


def _brace_delta(text: str) -> int:
    code = re.sub(r'"(\\.|[^"\\])*"|\'(\\.|[^\'\\])*\'|//[^\n]*|/\*.*?\*/', "", text, flags=re.S)
    return code.count("{") - code.count("}")


def _same_braces(block: EditBlock, old: str, new: str) -> None:
    """A range/function replacement must open and close as many blocks as the lines it replaces
    (P3 r2: line ranges that split a block produced `expected identifier` build failures)."""
    before, after = _brace_delta(old), _brace_delta(new)
    if before != after:
        where = f"lines {block.start}-{block.end}" if block.kind == "range" else block.name
        raise EditError(
            f"{block.path}: your replacement of {where} changes the brace balance "
            f"({before:+d} in the original lines, {after:+d} in yours); replace whole statements "
            "or blocks"
        )


def _definition(lines: list[str], name: str) -> tuple[int, int]:
    """(first, last) 0-based lines of the definition of `name`, by brace matching."""
    call = re.compile(rf"(^|[\s*&(]){re.escape(name)}\s*\(")
    for i, line in enumerate(lines):
        if not call.search(line) or line.lstrip().startswith(("#", "//", "*", "return ")):
            continue
        # A definition: the parameter list is followed by '{' before any ';'.
        depth, j, opened = 0, i, False
        tail = "\n".join(lines[i : i + 12])
        brace, semi = tail.find("{"), tail.find(";")
        if brace < 0 or (0 <= semi < brace):
            continue
        start = i
        prev = lines[i - 1].strip() if i else ""
        if prev and not prev.endswith((";", "}", "{", "*/")) and not prev.startswith(("#", "//")):
            start = i - 1  # return type on its own line ("static int\nname(...)")
        for j in range(i, len(lines)):
            code = re.sub(r'"(\\.|[^"\\])*"|\'(\\.|[^\'\\])*\'|//.*', "", lines[j])
            depth += code.count("{") - code.count("}")
            opened = opened or "{" in code
            if opened and depth == 0:
                return start, j
        raise EditError(f"function {name}: unbalanced braces")
    raise EditError(f"function {name}: no definition found")


def apply_function(source: str, block: EditBlock) -> str:
    lines = source.splitlines()
    first, last = _definition(lines, block.name)
    _same_braces(block, "\n".join(lines[first : last + 1]), block.replace)
    lines[first : last + 1] = block.replace.splitlines()
    return "\n".join(lines) + ("\n" if source.endswith("\n") else "")


def apply_blocks(
    files: dict[str, str],
    blocks: list[EditBlock],
    shown: dict[str, list[tuple[int, int]]] | None = None,
) -> tuple[dict[str, str], list[str]]:
    """Apply blocks to {path: source}; unknown paths are an error (scope is the caller's list).

    With a single file in scope every block targets it, whatever path the model wrote.
    `shown`: {path: [(first, last line), ...]} the worker saw; line-range edits must stay inside
    one of them. Range and function blocks address the original file, so they are applied
    bottom-up (by position) after SEARCH blocks would have shifted nothing."""
    out = dict(files)
    strategies = []
    resolved = []
    seen: set[tuple] = set()
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
            block = EditBlock(
                matches[0],
                block.search,
                block.replace,
                block.kind,
                block.start,
                block.end,
                block.name,
            )
        key = (
            block.path,
            block.kind,
            block.start,
            block.end,
            block.name,
            block.search,
            block.replace,
        )
        if key not in seen:  # the same block twice is one edit, not an overlap
            seen.add(key)
            resolved.append(block)
    # Line ranges first, bottom-up, on the original numbering; then functions; then SEARCH
    # blocks, which match by content and do not care about shifted lines.
    ranges = sorted((b for b in resolved if b.kind == "range"), key=lambda b: (b.path, -b.start))
    for prev, cur in zip(ranges, ranges[1:], strict=False):
        if prev.path == cur.path and cur.end >= prev.start:
            raise EditError(
                f"{cur.path}: line ranges {cur.start}-{cur.end} and {prev.start}-{prev.end} overlap"
            )
    for block in ranges:
        out[block.path] = apply_range(out[block.path], block, (shown or {}).get(block.path))
        strategies.append("line_range")
    for block in (b for b in resolved if b.kind == "function"):
        out[block.path] = apply_function(out[block.path], block)
        strategies.append("function")
    for block in (b for b in resolved if b.kind == "search"):
        out[block.path], how = apply_block(out[block.path], block)
        strategies.append(how)
    # Keep a CRLF file CRLF: the line-based edits join with "\n", which would turn a one-line fix
    # into a whole-file diff (gpac #4006 on a Windows checkout).
    for path, text in out.items():
        if text != files[path] and "\r\n" in files[path]:
            out[path] = text.replace("\r\n", "\n").replace("\n", "\r\n")
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
