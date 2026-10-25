"""`leakproof init`: draft a leakproof.toml for a C/C++ repository (review #8 order 4).

    leakproof init <repo-dir> [--issue-text FILE] [--out PATH]

Deterministic: the build system (meson, CMake, autotools, make, in that order), a build command
that keeps the sanitizer flags, the test command, and the editable globs. The sanitizer flags
travel in $CC as well as $CFLAGS, because many Makefiles assign CFLAGS and would drop them.
From an issue's text (optional), Nemotron Nano extracts the command the reporter ran and the
input they gave inline; the draft's reproducer runs that command on /tmp/poc. Everything is a
draft: `leakproof fix` checks that the build succeeds and the reproducer trips a sanitizer.
"""

from __future__ import annotations

import os
import re
from collections import Counter
from pathlib import Path
from typing import Any

from leakproof.cases.project import SKIP_DIRS

# $CC carries the flags so a Makefile's own `CFLAGS = ...` cannot drop them; the link step uses $CC.
CC = 'CC="clang $CFLAGS" CXX="clang++ $CXXFLAGS"'
NOT_EDITABLE = {"test", "tests", "testing", "fuzz", "fuzzing", "example", "examples", "doc", "docs"}
NOT_EDITABLE |= {"perf", "bench", "benchmark", "benchmarks", "third_party", "vendor", "external"}
SRC_EXT = {".c", ".h", ".cc", ".cpp", ".cxx", ".hh", ".hpp"}

ISSUE_SCHEMA = {
    "type": "object",
    "properties": {
        "program": {
            "type": "string",
            "description": "the binary the reporter ran, as a path relative to the repo root "
            "(e.g. ./jq, build/tool), or empty if none is shown",
        },
        "args": {
            "type": "string",
            "description": "the arguments after the program, with the crash input file "
            "replaced by {POC}; empty if none",
        },
        "input_kind": {"type": "string", "enum": ["file", "stdin", "arg", "none"]},
        "input_text": {
            "type": "string",
            "description": "the crash input exactly as given inline in the issue "
            "(a file's content, stdin, or the argument), empty if it is only attached or linked",
        },
        "input_encoding": {
            "type": "string",
            "enum": ["text", "hex_bytes", "c_escapes"],
            "description": "how input_text is written in the issue: plain text, a list of hex "
            "byte values (0x41, \\x41, 41 42), or a C string with escapes",
        },
        "input_ext": {"type": "string", "description": "file extension for the input, e.g. .json"},
    },
    "required": ["program", "args", "input_kind", "input_text", "input_encoding", "input_ext"],
}
ISSUE_SYSTEM = (
    "You read a bug report about a memory-safety crash in a C/C++ project and extract how the "
    "reporter reproduced it. Copy commands and inputs verbatim; never invent an input that is "
    "not written in the issue. Answer with the JSON object only."
)


def _files(repo: Path) -> list[Path]:
    out = []
    for dirpath, dirs, names in os.walk(repo):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
        out += [Path(dirpath) / n for n in names]
    return out


def _make_targets(makefile: Path) -> set[str]:
    text = makefile.read_text(encoding="utf-8", errors="replace")
    return set(re.findall(r"^([A-Za-z0-9_.-]+)\s*:(?!=)", text, re.M))


def detect(repo: Path) -> dict[str, Any]:
    """{system, build, test} for the repo's own build, with the sanitizer flags kept.

    Order: meson, autotools, a top-level Makefile (usually the maintained entry point when a
    CMakeLists.txt sits next to it), CMake.
    """
    has = lambda name: (repo / name).exists()  # noqa: E731
    prep = "find . -name '*.sh' -exec chmod +x {} + ; "  # exec bits get lost on some checkouts
    if has("meson.build"):
        tests = "test(" in (repo / "meson.build").read_text(errors="replace")
        return {
            "system": "meson",
            "build": prep + "meson setup build -Db_lundef=false -Dbuildtype=debug "
            '-Dc_args="$CFLAGS" -Dcpp_args="$CXXFLAGS" -Dc_link_args="$LDFLAGS" '
            '-Dcpp_link_args="$LDFLAGS" && ninja -C build',
            "test": "meson test -C build" if tests else None,
        }
    autoconf = has("configure.ac") or has("configure.in")
    if has("configure") and not autoconf:  # toybox-style hand-written configure scripts are not
        autoconf = "Autoconf" in (repo / "configure").read_text(errors="replace")[:4000]
    if autoconf:
        gen = "" if has("configure") else "autoreconf -fi && "
        return {
            "system": "autotools",
            "build": prep + gen + f"./configure --disable-shared {CC} && make -j4",
            "test": "make check",
        }
    for name in ("GNUmakefile", "makefile", "Makefile"):
        if has(name):
            targets = _make_targets(repo / name)
            config = "make defconfig > /dev/null && " if "defconfig" in targets else ""
            test = (
                "make check" if "check" in targets else "make test" if "test" in targets else None
            )
            if test is None and has("scripts/test.sh"):
                test = "bash scripts/test.sh"
            return {
                "system": "make",
                "build": prep + config + f"make -j4 {CC}",
                "test": test,
            }
    if has("CMakeLists.txt"):
        text = (repo / "CMakeLists.txt").read_text(errors="replace")
        return {
            "system": "cmake",
            "build": prep
            + 'cmake -S . -B build -DCMAKE_BUILD_TYPE=Debug -DCMAKE_C_FLAGS="$CFLAGS" '
            '-DCMAKE_CXX_FLAGS="$CXXFLAGS" -DCMAKE_EXE_LINKER_FLAGS="$LDFLAGS" '
            "-DBUILD_SHARED_LIBS=OFF && cmake --build build -j4",
            "test": "ctest --test-dir build --output-on-failure"
            if re.search(r"enable_testing|add_test|include\(CTest\)", text)
            else None,
        }
    return {"system": "none", "build": None, "test": None}


def editable(repo: Path) -> list[str]:
    """Globs for the directories that hold the project's own sources (not tests or examples)."""
    count: Counter[tuple[str, str]] = Counter()
    for f in _files(repo):
        rel = f.relative_to(repo)
        if f.suffix in SRC_EXT and not set(p.lower() for p in rel.parts[:-1]) & NOT_EDITABLE:
            count[(rel.parent.as_posix(), f.suffix)] += 1
    return [
        (f"{d}/*{ext}" if d != "." else f"*{ext}")
        for (d, ext), _ in sorted(count.items(), key=lambda kv: (-kv[1], kv[0]))[:8]
    ]


def from_issue(client: Any, text: str) -> tuple[dict[str, Any], float]:
    """Nano reads the issue: the reporter's command and inline input. Returns (fields, usd)."""
    value, res = client.structured(
        "nano",
        [
            {"role": "system", "content": ISSUE_SYSTEM},
            {"role": "user", "content": text[:40_000]},
        ],
        ISSUE_SCHEMA,
        purpose="init_issue",
        max_completion_tokens=4000,
        temperature=0,
    )
    return value, res.usd


def reproduce_cmd(issue: dict[str, Any]) -> str | None:
    prog = issue.get("program", "").strip()
    if not prog:
        return None
    if "/" not in prog:
        prog = "./" + prog
    args = issue.get("args", "").strip()
    kind = issue.get("input_kind")
    if kind == "file":
        if "{POC}" not in args:
            # The reporter's own file name: the last argument that is not an option.
            words = args.split()
            files = [i for i, w in enumerate(words) if not w.startswith("-")]
            if files:
                words[files[-1]] = "{POC}"
            args = " ".join(words) if files else f"{args} {{POC}}"
        return f"{prog} {args.replace('{POC}', '/tmp/poc')}".strip()
    if kind == "stdin":
        args = re.sub(r"<?\s*\{POC\}", "", args).strip()
        return f"{prog} {args} < /tmp/poc".replace("  ", " ")
    if kind == "arg":
        if "{POC}" in args:
            return f"{prog} {args.replace('{POC}', '"$(cat /tmp/poc)"')}"
        return f'{prog} {args} "$(cat /tmp/poc)"'.replace("  ", " ")
    return f"{prog} {args}".strip()


def draft(
    repo: Path,
    issue: dict[str, Any] | None = None,
    name: str | None = None,
    src: str = ".",
    poc_dir: str = ".",
) -> str:
    """The leakproof.toml text. Unknowns are left as commented TODO lines.

    `src` is the repo relative to the config file; `poc_dir` is where the input file is written,
    relative to the repo (the config's `poc` is resolved against `src`).
    """
    d = detect(repo)
    lines = [
        f"# Drafted by `leakproof init` ({d['system']}); check it with `leakproof fix`.",
        "[project]",
        f'name = "{re.sub(r"[^A-Za-z0-9_.-]", "_", name or repo.resolve().name)}"',
        f'src = "{src}"',
    ]
    lines.append(f"build = '''{d['build']}'''" if d["build"] else "# TODO build = '''...'''")
    rep = reproduce_cmd(issue) if issue else None
    if rep:
        lines.append(f"reproduce = '''{rep}'''")
        if issue and poc_bytes(issue) is not None:
            poc = f"poc{issue.get('input_ext') or '.bin'}"
            lines.append(f'poc = "{poc if poc_dir == "." else f"{poc_dir}/{poc}"}"')
        elif "/tmp/poc" in rep:
            lines.append('# TODO poc = "..."  # the issue attaches or links its input: add it')
        prog = issue["program"].strip().removeprefix("./") if issue else ""
        if prog:
            lines.append(f'artifact = "{prog}"')
    else:
        lines.append("# TODO reproduce = '''./your-binary /tmp/poc'''  # must trip a sanitizer")
    lines.append(f"test = '''{d['test']}'''" if d["test"] else "# test = '''...'''  # optional")
    globs = editable(repo)
    if globs:
        lines.append("editable = [" + ", ".join(f'"{g}"' for g in globs) + "]")
    return "\n".join(lines) + "\n"


def poc_bytes(issue: dict[str, Any]) -> bytes | None:
    """The input as bytes, decoded deterministically from how the issue wrote it."""
    text = issue.get("input_text") or ""
    if issue.get("input_kind") in (None, "none") or not text:
        return None
    enc = issue.get("input_encoding", "text")
    if enc == "hex_bytes":
        pairs = re.findall(r"(?:0x|\\x)?([0-9a-fA-F]{2})\b", text)
        return bytes(int(h, 16) for h in pairs) or None
    if enc == "c_escapes" or ("\n" not in text and "\\n" in text):
        # Escapes kept literal (\n, \t, \", \\, \xNN) become the bytes they stand for.
        data = text.encode("latin-1", "backslashreplace").decode("unicode_escape").encode("latin-1")
    else:
        data = text.encode()
    # An argument is used verbatim; a file or stdin input ends with the newline it was typed with.
    if issue["input_kind"] != "arg" and enc == "text" and not data.endswith(b"\n"):
        data += b"\n"
    return data


def write_poc(out_dir: Path, issue: dict[str, Any]) -> Path | None:
    data = poc_bytes(issue)
    if data is None:
        return None
    path = out_dir / f"poc{issue.get('input_ext') or '.bin'}"
    path.write_bytes(data)
    return path
