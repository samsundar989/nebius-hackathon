"""Gate checks 5-7 without a fuzz harness (D-0078). Gate-side only; workers never import this.

Most real projects have a reproducer command and an input file, not a libFuzzer harness. For a
bring-your-own project whose reproducer reads /tmp/poc (directly, or as an argument through
`"$(cat /tmp/poc)"`), the gate generates inputs from the PoC - the amplification operators,
truncations and seeded byte mutations - and runs the reproducer on each, unpatched and patched,
under ASan + UBSan + LeakSanitizer:

  refuzz        a patched crash with the target's signature (kind + function + file) means the
                fix is incomplete (`same bug`); a signature the unpatched build never shows is a
                new crash; a signature it also shows is pre-existing and only reported
  differential  on every input where the unpatched build is sanitizer-clean, the patched build
                must give the same exit status and stdout
  safe_fix      leaks are sanitizer reports in the same run, judged by the refuzz rule

Deterministic: the mutations come from a fixed seed, so a re-judge sees the same inputs.
"""

from __future__ import annotations

import random
import shlex
from dataclasses import dataclass, field

from leakproof import gate_fuzz as gf

LP = gf.LP
N_MUTATIONS = 200
MAX_INPUT = 1 << 16
PER_INPUT_TIMEOUT = 5
MAX_REPORTS = 40
MARK = "@@LPGATE@@"


def generate(poc: bytes, seed: int = 1) -> list[tuple[str, bytes]]:
    """Inputs derived from the PoC: amplified, truncated, mutated; de-duplicated, PoC excluded."""
    out = list(gf.amplify(poc))
    n = len(poc)
    for k in range(1, 8):
        out.append((f"trunc_{k}of8", poc[: n * k // 8]))
    rng = random.Random(seed)
    for i in range(N_MUTATIONS if n else 0):
        b = bytearray(poc)
        for _ in range(rng.choice((1, 1, 2, 4))):
            op = rng.randrange(4)
            pos = rng.randrange(len(b) + 1)
            if op == 0 and b:
                b[min(pos, len(b) - 1)] ^= 1 << rng.randrange(8)
            elif op == 1:
                b.insert(pos, rng.randrange(256))
            elif op == 2 and b:
                del b[min(pos, len(b) - 1)]
            elif b:
                # Splice: repeat a slice of the PoC itself at a random point.
                a = rng.randrange(len(b))
                b[pos:pos] = b[a : a + rng.randrange(1, 9)]
        out.append((f"mut_{i:03d}", bytes(b)))
    seen, uniq = {poc}, []
    for name, data in out:
        if data not in seen and len(data) <= MAX_INPUT:
            seen.add(data)
            uniq.append((name, data))
    return uniq


def script(names: list[str], repro: str, env: dict[str, str] | None = None) -> str:
    """Run the reproducer once per generated input (copied to /tmp/poc); emit one row per input,
    `name rc stdout_md5 signature`, and the first reports as sections `cli_rep_<name>`."""
    exports = "".join(f"export {k}={shlex.quote(v)}; " for k, v in (env or {}).items())
    files = " ".join(shlex.quote(n) for n in names)
    return f"""
{exports}cp /tmp/poc {LP}/poc.orig 2>/dev/null; : > {LP}/cli_rows; nrep=0
for f in {files}; do
  cp {LP}/gen/$f /tmp/poc
  timeout {PER_INPUT_TIMEOUT} bash {LP}/repro.sh > {LP}/o 2> {LP}/e < /dev/null; rc=$?
  sig=$({gf.SIG} {LP}/e | tr ' ' '_')
  echo "$f $rc $(md5sum < {LP}/o | cut -c1-12) $sig" >> {LP}/cli_rows
  if [ -n "$sig" ] && [ $nrep -lt {MAX_REPORTS} ]; then nrep=$((nrep+1))
    printf '\\n{MARK} cli_rep_%s\\n' "$f"; {gf.report_cmd(f"{LP}/e")} | head -c 3000; fi
done
cp {LP}/poc.orig /tmp/poc 2>/dev/null
printf '\\n{MARK} cli_rows\\n'; cat {LP}/cli_rows
"""


def files(inputs: list[tuple[str, bytes]], repro: str) -> dict[str, bytes]:
    out = {f"{LP}/gen/{n}": d for n, d in inputs}
    out[f"{LP}/repro.sh"] = (repro + "\n").encode()
    return out


@dataclass
class Run:
    rows: dict[str, gf.Row] = field(default_factory=dict)
    reports: dict[str, str] = field(default_factory=dict)

    @classmethod
    def parse(cls, sec: dict[str, str]) -> Run:
        return cls(
            gf.parse_rows(sec.get("cli_rows", "")),
            {k.removeprefix("cli_rep_"): v for k, v in sec.items() if k.startswith("cli_rep_")},
        )

    def key(self, name: str) -> tuple[str, str] | None:
        r = self.rows.get(name)
        if r is None or not r.sig:
            return None
        k = gf.crash_key(self.reports.get(name, ""), r.rc)
        return (gf._norm(k[0]), k[1]) if k else (gf._norm(r.sig.rsplit(":_", 1)[-1]), "")


def judge(
    base: Run, patched: Run, target: tuple[str, str]
) -> tuple[tuple[str, str], tuple[str, str]]:
    """(refuzz (status, detail), differential (status, detail)) from the two runs."""
    if not base.rows:
        return ("inconclusive", "no rows from the unpatched run"), ("inconclusive", "")
    if not patched.rows:
        return ("inconclusive", "no rows from the patched run"), ("inconclusive", "")
    base_keys = {k for n in base.rows if (k := base.key(n))}
    same, new, pre, changed = [], [], set(), []
    for name, b in base.rows.items():
        p = patched.rows.get(name)
        if p is None:
            changed.append(f"{name}: no result")
            continue
        pk = patched.key(name)
        if pk is not None:
            if pk[0] == target[0] and pk[1] == target[1]:
                same.append(f"{name} ({pk[0]} at {pk[1]})")
            elif pk in base_keys:
                pre.add(pk)
            else:
                new.append(f"{name} ({pk[0]} at {pk[1] or '?'})")
        elif not b.sig and b.rc != "124" and (p.rc, p.out) != (b.rc, b.out):
            changed.append(f"{name}: exit {b.rc}->{p.rc}, stdout {b.out}->{p.out}")
    n = len(base.rows)
    note = f"{n} generated inputs" + (
        f"; {len(pre)} pre-existing signature(s) not attributed" if pre else ""
    )
    if same:
        refuzz = (
            "fail",
            f"same bug: the target crash recurs on {same[0]} ({len(same)} input(s)); {note}",
        )
    elif new:
        refuzz = (
            "fail",
            f"new crash on {new[0]} ({len(new)} input(s)), not seen unpatched; {note}",
        )
    else:
        refuzz = ("pass", f"{note}: no crash attributable to the patch")
    clean = sum(1 for b in base.rows.values() if not b.sig and b.rc != "124")
    if changed:
        diff = (
            "fail",
            f"behaviour changed on {changed[0]} ({len(changed)} of {clean} clean inputs)",
        )
    else:
        diff = ("pass", f"{clean} inputs clean unpatched: same exit status and stdout")
    return refuzz, diff
