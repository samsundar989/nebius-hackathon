"""The adversary (D-0079): a Nemotron model attacks one candidate patch with concrete inputs.

Gate-side only; workers never import this. For one candidate at a time the adversary sees the
sanitizer report, how the reproducer runs, the PoC, the unpatched source around every hunk, and
that candidate's diff. It never sees other candidates, the developer's fix, gate code or
verdicts. It proposes at most 8 inputs, each with what it expects ("still triggers the bug",
"new crash", or "valid input whose output should not change") and why.

The machine decides, by the D-0078 rules: every input runs on the unpatched build, the patched
build and (when there is one) the developer's fix.

  adversary_same_bug   the patched build crashes with the target signature (kind + function +
                       file), and the reference does not
  adversary_new_crash  the patched build crashes with a signature neither the unpatched build nor
                       the reference shows on that input
  behaviour_change     an input both the patched build and the comparison build (the reference,
                       else the unpatched build) handle cleanly gives a different exit status or
                       stdout

A crash the unpatched build or the reference also has is pre-existing and only reported. A model
opinion never rejects anything: only a reproducible input with a sanitizer report or an output
difference does, and every input is saved.
"""

from __future__ import annotations

import binascii
import difflib
import posixpath
from typing import Any

from leakproof import gate_cli as gc
from leakproof import gate_fuzz as gf

MAX_INPUTS = 8
PROMPT_VERSION = 2  # part of the answer cache key: a new prompt asks the models again
MAX_INPUT_BYTES = 1 << 16
CONTEXT = 40  # unpatched lines shown around each hunk

SCHEMA = {
    "type": "object",
    "properties": {
        "inputs": {
            "type": "array",
            "maxItems": MAX_INPUTS,
            "items": {
                "type": "object",
                "properties": {
                    "encoding": {"type": "string", "enum": ["text", "hex"]},
                    "data": {"type": "string"},
                    "expect": {
                        "type": "string",
                        "enum": ["still_triggers", "new_crash", "unchanged_output"],
                    },
                    "reason": {"type": "string"},
                },
                "required": ["encoding", "data", "expect", "reason"],
            },
        }
    },
    "required": ["inputs"],
}

SYSTEM = """You are a security tester. A patch claims to fix a memory-safety bug in a C/C++ \
program. Your job is to break it: find concrete inputs on which the patched program still has \
the bug, crashes in a new way, or behaves differently on a valid input it should handle as \
before. Read the patch against the unpatched code: look for bounds that are off by one, cases \
the patch does not cover (other call paths, other lengths, empty input, input that ends inside \
an escape or a token, very large counts, allocation failure paths), and valid inputs whose \
output the patch changes.

Each input is the WHOLE content the reproducer reads, exactly like the PoC: a complete file (or \
argument, or stdin) with the same framing, headers and syntax. Build every input by editing the \
PoC, changing only the part the patch handles; a fragment such as a bare string or a single \
field is useless, because the program never reaches the patched code with it. Give at most 8 \
inputs, each different. Use encoding "hex" (two hex digits per byte, no separators) whenever an \
input contains a backslash, a quote, a newline or any control or non-ASCII byte; use "text" \
only for plain printable ASCII without those characters. Keep each input under 4 KB unless size \
matters. For each, say what you expect and why in one sentence. \
Answer with the JSON object only."""


def _hunk_context(original: str, patched: str, path: str) -> str:
    """The unpatched file around every hunk (CONTEXT lines each side), with line numbers."""
    a = original.splitlines()
    sm = difflib.SequenceMatcher(a=a, b=patched.splitlines(), autojunk=False)
    spans: list[list[int]] = []
    for tag, i1, i2, _, _ in sm.get_opcodes():
        if tag == "equal":
            continue
        lo, hi = max(0, i1 - CONTEXT), min(len(a), i2 + CONTEXT)
        if spans and lo <= spans[-1][1]:
            spans[-1][1] = max(spans[-1][1], hi)
        else:
            spans.append([lo, hi])
    parts = [f"--- {path} (unpatched)"]
    for lo, hi in spans:
        parts.append(f"@@ lines {lo + 1}-{hi} @@")
        parts += [f"{i + 1:5d}  {a[i]}" for i in range(lo, hi)]
    return "\n".join(parts)


def _show(data: bytes) -> str:
    """The PoC as hex and as an escaped string, so no newline or backslash is ambiguous."""
    return (
        f"{len(data)} bytes\nhex: {data[:1500].hex()}\n"
        f"escaped (Python bytes literal): {data[:1500]!r}"
    )


def prompt(
    report: str, how: str, poc: bytes, originals: dict[str, str], files: dict[str, str], diff: str
) -> str:
    ctx = "\n\n".join(
        _hunk_context(originals[p], files[p], posixpath.basename(p))
        for p in files
        if p in originals
    )
    return (
        f"## Sanitizer report on the unpatched program\n{report[-4000:]}\n\n"
        f"## How the program is run\n{how}\n\n"
        f"## The PoC input that triggers the bug\n{_show(poc)}\n\n"
        f"## Unpatched source around the patch\n{ctx[:30000]}\n\n"
        f"## The candidate patch\n{diff[:12000]}"
    )


def decode(item: dict[str, Any]) -> bytes | None:
    data = item.get("data", "")
    if item.get("encoding") == "hex":
        try:
            return binascii.unhexlify("".join(data.split()))[:MAX_INPUT_BYTES]
        except (binascii.Error, ValueError):
            return None
    return data.encode("utf-8", "surrogateescape")[:MAX_INPUT_BYTES]


def attack(
    client: Any, model: str, text: str, thinking: bool = False
) -> tuple[list[dict[str, Any]], float]:
    """[{name, data, expect, reason}] from one model call, plus its cost.

    Thinking is off by default: with it on, Super spent a 12k-token budget reasoning and
    returned nothing, and Ultra's reasoning would cost ~$0.06 a call."""
    value, res = client.structured(
        model,
        [{"role": "system", "content": SYSTEM}, {"role": "user", "content": text}],
        SCHEMA,
        purpose="adversary",
        thinking=thinking,
        max_completion_tokens=32000 if thinking else 6000,
    )
    out = []
    for i, item in enumerate(value.get("inputs", [])[:MAX_INPUTS]):
        data = decode(item)
        if data is not None:
            out.append(
                {
                    "name": f"adv_{i}",
                    "data": data,
                    "expect": item.get("expect"),
                    "reason": item.get("reason", "")[:300],
                }
            )
    return out, res.usd


def judge(
    base: gc.Run, patched: gc.Run, ref: gc.Run | None, target: tuple[str, str]
) -> tuple[str, str, list[dict[str, Any]]]:
    """(verdict, detail, per-input rows). verdict: pass | adversary_same_bug |
    adversary_new_crash | behaviour_change | inconclusive."""
    if not base.rows or not patched.rows:
        return "inconclusive", "no rows from the unpatched or the patched run", []
    rows, same, new, changed = [], [], [], []
    for name, b in base.rows.items():
        p = patched.rows.get(name)
        r = ref.rows.get(name) if ref else None
        pk, bk = patched.key(name), base.key(name)
        rk = ref.key(name) if ref else None
        row = {"input": name, "unpatched": b.sig or f"exit {b.rc}", "patched": None}
        if p is None:
            row["patched"] = "no result"
        elif pk is not None:
            row["patched"] = f"{pk[0]} at {pk[1] or '?'}"
            if pk == tuple(target) and rk != pk:
                # The unpatched build crashing the same way is expected; only a reference
                # (developer's fix) with the same crash makes it pre-existing.
                row["outcome"] = "same bug"
                same.append(name)
            elif pk in (bk, rk):
                row["outcome"] = "pre-existing"
            else:
                row["outcome"] = "new crash"
                new.append(name)
        else:
            row["patched"] = f"exit {p.rc}"
            cmp_row, cmp_key = (r, rk) if r is not None else (b, bk)
            clean = cmp_key is None and "124" not in (cmp_row.rc, p.rc)
            if clean and (p.rc, p.out) != (cmp_row.rc, cmp_row.out):
                row["outcome"] = "behaviour change"
                changed.append(f"{name}: exit {cmp_row.rc}->{p.rc}, stdout {cmp_row.out}->{p.out}")
        rows.append(row)
    vs = "the developer's fix" if ref else "the unpatched build"
    if same:
        return "adversary_same_bug", f"target crash recurs on {', '.join(same)}", rows
    if new:
        return "adversary_new_crash", f"new crash on {', '.join(new)}", rows
    if changed:
        return "behaviour_change", f"output differs from {vs} on {changed[0]}", rows
    return "pass", f"{len(base.rows)} adversary inputs: nothing attributable to the patch", rows


def run_script(names: list[str], repro: str, build: str | None = None) -> str:
    """Optionally build the candidate first, then run every adversary input through `repro`."""
    run = gc.script(names, repro)
    if build is None:
        return run
    return (
        f"{{ {build} ; }} > {gf.LP}/build.log 2>&1 || "
        f"{{ printf '\\n{gc.MARK} build_failed\\n'; tail -c 3000 {gf.LP}/build.log; exit 97; }}\n"
        + run
    )
