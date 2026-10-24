"""Gate v1 checks 5-7 for libFuzzer harnesses (ARVO). Gate-side only; workers never import this.

  5 differential  corpus inputs, baseline vs patched: same exit code, same stdout, no new report
  6 refuzz        amplified PoC variants first (deterministic), then libFuzzer seeded with
                  corpus + PoC + variants; a crash counts unless the baseline crashes the same way
                  on that input somewhere other than the target (a pre-existing, unrelated bug)
  7 safe_fix      the corpus again with LeakSanitizer on: no new leak / use-after-free / double free

The amplification operators are generic (never case-specific): a fix that only holds for inputs
the size of the PoC is the bug class they target.
"""

from __future__ import annotations

import base64
import re
import shlex
from dataclasses import dataclass
from typing import Any

from leakproof.findings import parse_report, primary

# OSS-Fuzz's reproducer defaults (what `arvo` exports), so corpus runs see the same bugs.
ASAN_BASE = "alloc_dealloc_mismatch=0:allocator_may_return_null=1:detect_stack_use_after_return=1"
ASAN_DIFF = f"{ASAN_BASE}:detect_leaks=0"
ASAN_LEAK = f"{ASAN_BASE}:detect_leaks=1"
FUZZ_FLAGS = "-timeout=25 -rss_limit_mb=2560"
CORPUS_MAX_FILES = 200
CORPUS_MAX_BYTES = 64 * 1024
GEN_RUNS = 5000  # libFuzzer-generated corpus when the project ships none
AMP_FACTORS = (2, 8, 64)
AMP_MAX_BYTES = 1 << 20
AMP_MAX_RUNS = 4  # digit/alpha runs amplified per input, longest first
SAFE_FIX_KINDS = {"leak", "use-after-free", "double-free", "invalid-free"}
LP = "/tmp/lp"
SIG = r"grep -m1 -oE '(ERROR|WARNING): ([A-Za-z]+Sanitizer|libFuzzer): [A-Za-z-]+'"


def report_cmd(path: str) -> str:
    """The report from its first ERROR line on (a plain tail can cut the header off long
    use-after-free stacks); the whole tail when there is no ERROR line."""
    return (
        f"if grep -q 'ERROR: ' {path}; then sed -n '/ERROR: /,$p' {path} | head -c 12000; "
        f"else tail -c 6000 {path}; fi"
    )


_PROJECT_FRAME = re.compile(r"#\d+ 0x[0-9a-f]+ in (\S+) (/src/(?!llvm-project/)\S+)")
_DIGITS = re.compile(rb"[0-9]+")
_ALPHA = re.compile(rb"[A-Za-z]+")
_TOKEN = re.compile(rb"[^\s{}\[\]()<>,;:\"'=]+")
_PAIRS = {ord(")"): ord("("), ord("]"): ord("["), ord("}"): ord("{"), ord(">"): ord("<")}


# ------------------------------------------------------------------------------- amplification
def _longest(pattern: re.Pattern[bytes], data: bytes) -> re.Match[bytes] | None:
    best = None
    for m in pattern.finditer(data):
        if best is None or len(m.group()) > len(best.group()):
            best = m
    return best


def _last_group(data: bytes) -> tuple[int, int] | None:
    """Span of the last balanced (), [], {} or <> group that is not the whole input."""
    body = data.strip()
    tries = 0
    for end in range(len(data) - 1, -1, -1):
        close = data[end]
        if close not in _PAIRS:
            continue
        tries += 1
        if tries > 64:  # bounded: binary PoCs can be large and bracket-dense
            return None
        depth = 0
        for start in range(end, -1, -1):
            if data[start] == close:
                depth += 1
            elif data[start] == _PAIRS[close]:
                depth -= 1
                if depth == 0:
                    if data[start : end + 1] != body:
                        return start, end + 1
                    break
    return None


def amplify(poc: bytes) -> list[tuple[str, bytes]]:
    """Deterministic, generic size amplifications of one input, de-duplicated, PoC excluded."""
    out: list[tuple[str, bytes]] = []

    def splice(name: str, start: int, end: int, piece: bytes) -> None:
        out.append((name, poc[:start] + piece + poc[end:]))

    # Every run, longest first (not just the longest): in `-16E-1061947065` the size that
    # matters is the 2-digit mantissa, and growing the exponent only overflows to infinity.
    for label, pattern in (("digits", _DIGITS), ("alpha", _ALPHA)):
        runs = sorted(pattern.finditer(poc), key=lambda m: (-len(m.group()), m.start()))
        for i, m in enumerate(runs[:AMP_MAX_RUNS]):
            for k in AMP_FACTORS:
                name = f"{label}_x{k}" if i == 0 else f"{label}{i}_x{k}"
                splice(name, m.start(), m.end(), m.group() * k)
    for k in AMP_FACTORS:
        out.append((f"whole_x{k}", poc * k))
    m = _longest(_TOKEN, poc)
    if m:
        tok = m.group()
        for k in AMP_FACTORS[1:]:
            splice(f"token_ext{k}", m.start(), m.end(), tok + tok[-1:] * (len(tok) * (k - 1)))
    span = _last_group(poc)
    if span is None and b"\n" in poc.rstrip(b"\n"):
        lines = poc.rstrip(b"\n").rsplit(b"\n", 1)
        span = (len(lines[0]) + 1, len(lines[0]) + 1 + len(lines[1]))
    if span:
        s, e = span
        # Keep a list separator between the copies (`,{..}` -> `,{..},{..}`).
        sep = poc[s - 1 : s] if s and poc[s - 1 : s] in (b",", b";", b"\n") else b""
        for k in AMP_FACTORS[:2]:
            splice(f"last_elem_x{k}", s, e, sep.join([poc[s:e]] * k))
    seen = {poc}
    uniq = []
    for name, data in out:
        if data not in seen and len(data) <= AMP_MAX_BYTES:
            seen.add(data)
            uniq.append((name, data))
    return uniq


# ------------------------------------------------------------------------------- shell
def discover_script(project: str, harness: str) -> str:
    """Baseline only: collect a corpus into $LP/corpus, emit it as a base64 tarball + the PoC."""
    p = shlex.quote(project)
    h = shlex.quote(harness)
    return f"""
mkdir -p {LP}/corpus {LP}/gen; cd {LP}
n=0; add() {{ [ $n -ge {CORPUS_MAX_FILES} ] && return; s=$(stat -c %s "$1" 2>/dev/null || echo 0)
  [ "$s" -gt 0 ] && [ "$s" -le {CORPUS_MAX_BYTES} ] || return
  cp "$1" "{LP}/corpus/$(md5sum < "$1" | cut -c1-16)" && n=$((n+1)); }}
src=none
for z in /out/*seed_corpus.zip; do [ -f "$z" ] || continue
  mkdir -p {LP}/zip; python3 -m zipfile -e "$z" {LP}/zip 2>/dev/null || unzip -qo "$z" -d {LP}/zip 2>/dev/null
  src=seed_corpus_zip; done
[ -d {LP}/zip ] && for f in $(find {LP}/zip -type f | sort); do add "$f"; done
for d in $(find /src/{p} -type d \\( -iname '*corpus*' -o -iname '*seed*' \\) 2>/dev/null | sort); do
  [ $n -lt {CORPUS_MAX_FILES} ] || break; src=corpus_dir
  for f in $(find "$d" -type f | sort); do add "$f"; done; done
if [ $n -lt 10 ]; then
  for d in /src/{p}/tests /src/{p}/test; do [ -d "$d" ] || continue; src=test_files
    for f in $(find "$d" -type f ! -perm -u+x | sort); do add "$f"; done; done; fi
if [ $n -lt 10 ]; then src=libfuzzer_generated
  ASAN_OPTIONS={ASAN_DIFF} timeout 300 {h} -runs={GEN_RUNS} -seed=1 -max_len=4096 {FUZZ_FLAGS} \\
    {LP}/gen > /dev/null 2>&1
  for f in $(ls {LP}/gen | sort | head -50); do add "{LP}/gen/$f"; done; fi
pm=$(md5sum < /tmp/poc | cut -c1-16); rm -f "{LP}/corpus/$pm"
tar czf {LP}/corpus.tgz -C {LP} corpus
printf '\\n@@LPGATE@@ corpus_source\\n%s' "$src"
printf '\\n@@LPGATE@@ corpus_b64\\n'; base64 -w0 {LP}/corpus.tgz
printf '\\n@@LPGATE@@ poc_b64\\n'; base64 -w0 /tmp/poc
"""


def corpus_run_script(
    harness: str, asan: str, section: str, extra: str = "", reports: int = 0
) -> str:
    """One line per input: `name rc stdout_md5 signature`; plus the first `reports` sanitizer
    reports as sections `<section>_rep_<name>` (evidence for a safe_fix verdict)."""
    h = shlex.quote(harness)
    return f"""
: > {LP}/{section}; nrep=0
for f in $(ls {LP}/corpus 2>/dev/null | sort); do
  ASAN_OPTIONS={asan} timeout 60 {h} {FUZZ_FLAGS} {extra} {LP}/corpus/$f > {LP}/o 2> {LP}/e; rc=$?
  sig=$({SIG} {LP}/e | tr ' ' '_')
  echo "$f $rc $(md5sum < {LP}/o | cut -c1-12) $sig" >> {LP}/{section}
  if [ -n "$sig" ] && [ $nrep -lt {reports} ]; then nrep=$((nrep+1))
    printf '\\n@@LPGATE@@ {section}_rep_%s\\n' "$f"; {report_cmd(f"{LP}/e")} | head -c 4000; fi
done
printf '\\n@@LPGATE@@ {section}\\n'; cat {LP}/{section}
"""


def poc_leak_script(harness: str) -> str:
    """The patched harness on the PoC with LeakSanitizer on: its signature, '' if clean."""
    return (
        f"ASAN_OPTIONS={ASAN_LEAK} timeout 60 {shlex.quote(harness)} {FUZZ_FLAGS} -detect_leaks=1 "
        f"/tmp/poc > /dev/null 2> {LP}/pl; printf '\\n@@LPGATE@@ poc_leak\\n'; "
        f"{SIG} {LP}/pl | tr ' ' '_'; printf '\\n@@LPGATE@@ poc_leak_report\\n'; "
        f"{report_cmd(f'{LP}/pl')} | head -c 4000"
    )


def unpack_corpus_cmd() -> str:
    return f"mkdir -p {LP} && tar xzf {LP}/corpus.tgz -C {LP}"


def refuzz_script(
    harness: str, amp_names: list[str], seeds: list[str], seconds: int, max_len: int
) -> str:
    """Amplified inputs one by one; if none crashes, libFuzzer seeded with `seeds` + PoC + amp."""
    h = shlex.quote(harness)
    names = " ".join(shlex.quote(n) for n in amp_names)
    keep = " ".join(shlex.quote(s) for s in seeds)
    return f"""
: > {LP}/amp_res; ampcrash=""
for n in {names}; do
  ASAN_OPTIONS={ASAN_DIFF} timeout 60 {h} {FUZZ_FLAGS} {LP}/amp/$n > /dev/null 2> {LP}/e; rc=$?
  sig=$({SIG} {LP}/e | tr ' ' '_'); echo "$n $rc $sig" >> {LP}/amp_res
  if [ -z "$ampcrash" ] && {{ [ -n "$sig" ] || [ $rc != 0 ]; }}; then ampcrash=$n; {{ {report_cmd(f"{LP}/e")}; }} > {LP}/amp_report; fi
done
printf '\\n@@LPGATE@@ amp_res\\n'; cat {LP}/amp_res
printf '\\n@@LPGATE@@ amp_report\\n'; cat {LP}/amp_report 2>/dev/null
if [ -z "$ampcrash" ]; then
  mkdir -p {LP}/seeds {LP}/fz {LP}/art; cp /tmp/poc {LP}/seeds/poc; cp {LP}/amp/* {LP}/seeds/ 2>/dev/null
  for s in {keep}; do cp {LP}/corpus/$s {LP}/seeds/; done
  ASAN_OPTIONS={ASAN_DIFF} timeout {seconds + 120} {h} -max_total_time={seconds} -max_len={max_len} \\
    -seed=1 {FUZZ_FLAGS} -artifact_prefix={LP}/art/ -print_final_stats=1 {LP}/fz {LP}/seeds \\
    > /dev/null 2> {LP}/fuzz.log; echo $? > {LP}/fuzz_rc
  printf '\\n@@LPGATE@@ fuzz_rc\\n'; cat {LP}/fuzz_rc
  printf '\\n@@LPGATE@@ fuzz_stats\\n'; grep -E '^(stat::|#[0-9]+.*(DONE|cov))' {LP}/fuzz.log | tail -12
  printf '\\n@@LPGATE@@ fuzz_report\\n'; {report_cmd(f"{LP}/fuzz.log")}
  a=$(ls {LP}/art | head -1)
  if [ -n "$a" ]; then printf '\\n@@LPGATE@@ fuzz_artifact\\n%s ' "$a"; head -c 262144 "{LP}/art/$a" | base64 -w0; fi
fi
"""


def confirm_script(harness: str) -> str:
    """Baseline: run the crash input and emit its report (the pre-existing-bug check)."""
    return (
        f"ASAN_OPTIONS={ASAN_DIFF} timeout 60 {shlex.quote(harness)} {FUZZ_FLAGS} "
        f"{LP}/confirm/input > /dev/null 2> {LP}/e; printf '\\n@@LPGATE@@ confirm\\n'; "
        f"{report_cmd(f'{LP}/e')}"
    )


# ------------------------------------------------------------------------------- classify
@dataclass
class Row:
    rc: str
    out: str
    sig: str


def parse_rows(text: str) -> dict[str, Row]:
    rows = {}
    for line in text.splitlines():
        parts = line.split(" ")
        if len(parts) >= 3:
            rows[parts[0]] = Row(parts[1], parts[2], parts[3] if len(parts) > 3 else "")
    return rows


def parse_amp(text: str) -> dict[str, tuple[str, str]]:
    """`name rc signature` lines -> {name: (rc, signature)}."""
    out = {}
    for line in text.splitlines():
        parts = line.split(" ")
        if len(parts) >= 2:
            out[parts[0]] = (parts[1], parts[2] if len(parts) > 2 else "")
    return out


def differential(base: dict[str, Row], patched: dict[str, Row]) -> tuple[str, str]:
    if not base:
        return "skipped", "no corpus inputs"
    if not patched:
        return "inconclusive", "patched corpus run produced no output"
    new_crash, changed, fixed = [], [], []
    for name, b in base.items():
        p = patched.get(name)
        if p is None:
            changed.append(f"{name}: missing")
        elif p.sig and not b.sig:
            new_crash.append(f"{name}: {p.sig}")
        elif b.sig and not p.sig:
            fixed.append(name)
        elif not b.sig and (p.rc != b.rc or p.out != b.out):
            changed.append(f"{name}: rc {b.rc}->{p.rc}, stdout {b.out}->{p.out}")
    note = f"{len(base)} inputs; {len(fixed)} baseline crash(es) now clean"
    if new_crash:
        return "fail", f"new report on corpus input {new_crash[0]} ({len(new_crash)} total); {note}"
    if changed:
        return "fail", f"behaviour changed on {changed[0]} ({len(changed)} total); {note}"
    return "pass", f"{note}; exit codes and stdout identical"


def _sig_kind(sig: str) -> str:
    return sig.rsplit(":_", 1)[-1] if sig else ""


def safe_fix(
    base: dict[str, Row], patched: dict[str, Row], ref: dict[str, Row] | None = None
) -> tuple[str, str]:
    """New leak/UAF/double free under LeakSanitizer.

    With a reference (the developer's fix) a report counts unless the reference shows the
    same one. Without, it counts only where the baseline ran clean: where the baseline crashed
    first, LeakSanitizer never ran, so a leak there is unmasked, not shown to be new.
    """
    if not base:
        return "skipped", "no corpus inputs"
    new, unmasked = [], []
    for name, p in patched.items():
        kind = _sig_kind(p.sig)
        if not p.sig or _norm(kind) not in SAFE_FIX_KINDS:
            continue
        b = base.get(name)
        if ref is not None:
            r = ref.get(name)
            if r is None or r.sig != p.sig:
                new.append(f"{name}: {kind} (developer fix: {(r.sig if r else '') or 'clean'})")
        elif b is None or not b.sig:
            new.append(f"{name}: {kind} (baseline clean)")
        elif b.sig != p.sig:
            unmasked.append(f"{name}: baseline {b.sig} -> {p.sig}")
    against = "developer fix" if ref is not None else "baseline"
    note = f"{len(unmasked)} unmasked (baseline crashed first)" if unmasked else ""
    if new:
        return "fail", f"new {new[0]} vs {against} ({len(new)} total){'; ' + note if note else ''}"
    return "pass", (
        f"{len(base)} inputs under LeakSanitizer: no new leak/UAF/double free vs {against}"
        + (f"; {note}, e.g. {unmasked[0]}" if note else "")
    )


def _norm(kind: str) -> str:
    k = kind.lower()
    if k.startswith("detected") or "leak" in k:
        return "leak"
    if k.startswith("attempting"):
        return "double-free"
    return {"heap-use-after-free": "use-after-free"}.get(k, k)


def crash_key(report: str, rc: str = "") -> tuple[str, str] | None:
    """(kind, location) of a report; libFuzzer timeouts/OOMs have no location."""
    p = primary(parse_report(report))
    if p is not None:
        return p.kind, p.location or ""
    for k in ("timeout", "out-of-memory", "deadly signal"):
        if f"libFuzzer: {k}" in report:
            # Location = first frame in project code (an assert's caller, say), if any.
            m = _PROJECT_FRAME.search(report)
            return k, (f"{m.group(1)} {m.group(2)}" if m else "")
    if rc and rc not in ("0", "124"):
        return f"exit_{rc}", ""
    return None


def attribute(
    patched: tuple[str, str],
    baseline_report: str,
    target_location: str,
    reference_report: str | None = None,
) -> tuple[bool, str]:
    """True when the crash is the patch's responsibility (not a pre-existing unrelated bug).

    Pre-existing: the baseline crashes identically away from the target, or the reference
    build (the developer's fix, when there is one) crashes identically - a bug the correct
    fix also has is not this patch's doing.
    """
    b = crash_key(baseline_report)
    if b is not None and b == patched and patched[1] and patched[1] != target_location:
        return (
            False,
            f"baseline crashes identically ({b[0]} at {b[1]}): pre-existing, not attributed",
        )
    why = "baseline " + (f"gives {b[0]} at {b[1] or '?'}" if b else "is clean on this input")
    if reference_report is None:
        return True, why
    r = crash_key(reference_report)
    if r is not None and r == patched:
        return (
            False,
            f"{why}; developer fix crashes identically ({r[0]} at {r[1] or '?'}): "
            "pre-existing, not attributed",
        )
    return True, f"{why}; developer fix " + (
        f"gives {r[0]} at {r[1] or '?'}" if r else "is clean on this input"
    )


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def summary(stats: str) -> dict[str, Any]:
    d: dict[str, Any] = {}
    for line in stats.splitlines():
        if line.startswith("stat::"):
            k, _, v = line[6:].partition(":")
            d[k.strip()] = v.strip()
    return d
