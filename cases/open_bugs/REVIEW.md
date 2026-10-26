# Open bugs: review of every verified fix

Runs `runs/open_bugs_fix` (first attempt) and `runs/open_bugs_fix2` (retry with one repair round);
Ultra's advisory review in `runs/open_bugs/review.json`. Model spend for the whole exercise: $0.70
(fix $0.24 + $0.36, review $0.10). No developer fix exists, so each diff is judged against the
defect and the surrounding code, by Ultra and then by hand. The hand review decides.

Evidence for all of them is **weak** (D-0074): toybox has no runnable tests in our setup and no
fuzz harness, and berry's suite already fails 1 of 58 tests at HEAD with output the gate cannot
compare per test. The gate checked the reproducer only. That is exactly where the review matters.

## toybox #572 (`patch`, heap overflow in `unquote_file`): one fix is ready to propose

The defect: an escape sequence can consume the last character, so `s++` lands on the
terminator, the head-of-loop check `if (!s[1])` then reads past the end, and the loop keeps
writing. The minimal fix is to stop at the terminator (`if (!*s || !s[1]) error_exit(...)`).

| candidate | Ultra | hand review |
|---|---|---|
| H2·w1 | correct | **correct.** Pre-scans to the closing quote with the same escape rules and calls `error_exit("bad %s")` on the terminator; allocates exactly what is written. Verbose: the minimal one-line fix above is equivalent. **Ready to propose** (with the one-line alternative mentioned). |
| H3·w2 (the selected winner) | wrong | **wrong.** Grows the buffer with `realloc`, but still walks past the terminator; Ultra also notes no room is kept for the final `*t = 0`. |
| H1·w0, H1·w3 (same diff) | wrong | **wrong.** Allocates one byte more (`strlen(filename)+1`); still reads past the terminator, passes only this PoC. |

The pairwise winner selection (D-0070) picked a wrong candidate here over the correct one: the
first such case. Recorded in D-0076.

## toybox #571 (`getopt -l`, heap overflow in `parse_long_opt`): not ready

| candidate | Ultra | hand review |
|---|---|---|
| H2·w1 (the only verified one) | correct | **wrong.** `TT.l` is a `struct arg_list *` (`l*` in the option string: `-l` may repeat), but the patch iterates it as `const char *` and counts commas in the bytes of the list struct, so the allocation size is unrelated to the options given; a longer `-l a,b,c,d` overflows again. A correct fix counts commas over every `arg_list` entry (and keeps the zero entry `getopt_long` needs). Ultra did not have the `GLOBALS` definition in its context. |

## berry #544, format path (`mode_fixlen` stack overflow): not ready as written

Upstream already truncates an over-long specifier in `get_mode` (keeping the conversion
character); `mode_fixlen` then appends the integer length modifier `BE_INT_FMTLEN` past the end.

| candidate | Ultra | hand review |
|---|---|---|
| H1·w0 (the selected winner) | correct | **defensive.** Safe, but when the specifier is over-long it truncates the **length modifier** (`ll` → `l` or nothing) instead of the flags/width, so the format no longer matches the 64-bit argument on targets where `long` is 32 bits. The fix belongs in `get_mode`: reserve room for `BE_INT_FMTLEN`. |
| H3·w2 | correct | **defensive**, same reason (strncpy of a truncated `lenmode`). |
| H4·w3 | wrong | **wrong.** `snprintf(mode, …, "%.*s…", …, mode, …)`: source and destination overlap (undefined behaviour). |

## mjs #322 (use-after-free during `for…in` with `splice`): no fix

Both attempts were rejected (still crashing, then new misaligned accesses after the repair round):
the iterator's lifetime across garbage collection needs a design change the workers did not find.

## Funnel

14 issues triaged → 10 configured → 6 reproduce at upstream HEAD → 4 without an open fix PR →
3 verified by the gate → **1 ready to propose after review** (toybox #572, H2·w1, not the selected winner).

# Round 2 (review #7 order 5)

Runs `runs/open_bugs_r2` (one repair round each, $0.22). Hand review only (the Ultra review of
round 1 added little over it).

## cNBT #28, bug 1 (leak in `parse_unnamed_tag`): not ready — defensive

All four verified candidates (identical in substance) free the node's payload on `parse_error`.
That plugs this leak, but: (1) when `CHECKED_MALLOC(node)` fails, `parse_error` is reached with
`node == NULL` and the new `switch (node->type)` dereferences it (the original `free(NULL)` was
safe); (2) the cause stays — `parse_named_tag` keeps parsing after `read_string` fails, with `errno`
already set, so a successfully parsed payload is thrown away; a `TAG_COMPOUND` payload still leaks.
The issue's own suggestion (stop when `name == NULL`) addresses the cause. Evidence: medium (tests
none; harness with corpus differential, refuzz and LeakSanitizer all clean).

## jsmn #249 (out-of-bounds read in `example/jsondump.c`): not ready as written

The verified candidate (H2·w3) fixes the real off-by-one: a child at `t + 1 + j` has `count - 1 - j`
tokens left, not `count - j`. But when a malformed object's `size` claims more children than were
parsed, the loop continues after the count reaches 0: `dump(key, 0)` returns 0 and the next line
reads `key->size` at `t + count`, one past the last parsed token (in bounds only while the token
array has spare capacity). It needs `if (j >= count - 1) break;` before taking the next key. With
that addition it would be ready; jsmn's own tests pass. Upstream PR #250 (a `size` bounds check) was
closed by its author, not rejected.

## tidy-html5 #1177: no candidate

All eight attempts (round 1 and the repair round) failed to apply or build: the windows shown did
not include the end of `freeStack` in `lexer.c`, where the fix belongs.

## Funnel, round 2

16 issues triaged → 5 configured → 3 reproduce at HEAD (cNBT bug 2 is an allocation-size DoS the
gate does not judge; struct2json's demo exits 2 without a LeakSanitizer report in our build) →
2 verified → **0 ready to propose as written** (1 needs a one-line guard added in review).

## Both rounds

30 issues triaged → 7 reproduce at HEAD without an open fix PR, all attempted → 5 verified → 1 ready to propose (toybox #572, QUESTION 0017). Model spend $0.92 ($0.70 + $0.22).

## Round 3 (full product path: init → fix --adversary auto → package)

### elk #82 (`js_eval(buf, len)` reads past a bounded slice): ready to propose as a partial fix
All three verified candidates are the same one line: after the string loop, read `buf[js->tlen]`
only while `js->toff + js->tlen < js->clen`, so an unclosed string in a bounded slice stays
`TOK_ERR` (`next()` sets it first). That is the issue's own suggested fix for strings, and the
escape branches already stay in bounds. **Partial:** the issue reports a second defect, numbers
parsed with `strtod` past `len`; our reproducer covers only the string case, so that half is
untouched. elk's unit test fails at upstream HEAD (`test_basic` assertion), so the gate could not
use it ("verified, needs human review"). Package: `round3/cesanta_elk/generated/` (`Part of #82`).

### utf8.h #1 (`utf8_decode` reads continuation bytes past the end): ready to propose as a partial fix
The winner (H1·w0) checks `p[1]`, then `p[2]`, `p[3]` against the terminator before each read
(short-circuit `||`) and returns U+FFFD with `bytes_read = 1` for a truncated sequence; Super's
adversary input found nothing. Correct for the out-of-bounds read on NUL-terminated input (the
API's contract). **Partial:** the issue also asks for overlong, surrogate and non-continuation
rejection, which the patch does not add. Package: `round3/me7alix_utf8.h/generated/` (`Part of #1`).

### toybox #573 (mkpasswd `get_salt`): refused, correctly
Every patch bounded the loops but changed behaviour: the differential found different output on
43 of 169 inputs that ran clean unpatched, and none stops `s` running past the algorithm name.

### special-fun #17 (`facf`): refused, correctly; the planner misread the report
The planner blamed the table index; the overflow is `MAXNUMF`, declared `extern double` in
`facf.c` and defined `float` in `constf.c`, so every out-of-range call reads 8 bytes of a 4-byte
global. All four patches still crashed at the same line (`rejected:still_crashes`).

## Funnel, round 3

10 issues triaged → 4 configured (`leakproof init` drafted each; none had a build system the tool
could use, so the build and reproducer lines were hand-written) → 4 reproduce at HEAD →
2 verified → **0 complete fixes, 2 ready to propose as partial fixes** (QUESTION 0020).
Model spend $0.18.

## All three rounds

40 issues triaged → 11 reproduce at HEAD without an open fix PR, all attempted → 7 verified →
1 complete fix ready (toybox #572) + 2 partial fixes ready (elk #82, utf8.h #1). Model spend $1.10.
Machine-readable: `funnel.json` (published to NUMBERS and the dashboard).

## Review finding → caught by which check (D-0078 re-gate, D-0079 adversary)

Every distinct verified open-bugs diff re-gated with the harness-less checks: inputs generated
from the PoC (the PoC, an amplified copy, 8 truncations, 200 seeded mutations), run through the
reproducer with the patched and the unpatched build (`runs/open_bugs_regate/`, job 3850, $0).
Then the adversary (D-0079): Nemotron 3 Ultra and Nemotron 3 Super each read one candidate's diff
and proposed up to 8 inputs; only a sanitizer report confirmed by the machine rejects
(`runs/adversary/open/`, job 3862). The final version costs about $0.004 (Super) or $0.019 (Ultra)
per candidate; developing it, with three prompt versions and repair calls, cost $2.44 in total (D-0079).

| case | candidate | human review said | verdict now | caught by |
|---|---|---|---|---|
| toybox #571 | H2w1 | wrong: the overflow recurs on other `-l` strings | rejected:refuzz_same_bug (target crash on 7 of 169 generated inputs) | **generated inputs** |
| toybox #572 | M1 (one line) | correct | verified | — (no false reject, by either) |
| toybox #572 | H2w1 | correct | verified | — (no false reject, by either) |
| toybox #572 | H3w2, H1w0 | wrong: depends on the byte after the terminator | rejected:adversary_same_bug | **adversary inputs**: Ultra wrote the patch header `\n--- "\"` for H3w2 and `\n--- "\\` for H1w0 (escaped bytes): the same heap overflow in `unquote_file` at the target line; Super caught H1w0 only |
| berry #544 | H1w0, H3w2, H4w3 | defensive; the UB stays | verified | **still missed**: no generated or adversary input produced an ASan or UBSan report |
| jsmn #249 | H2w3 | needs a one-line guard for a residual edge | verified | **still missed**: the adversary's token-count inputs did not reach the edge |
| cNBT #28 | H1w0, H1w1 | defensive; the OOM path still dereferences NULL | verified (fuzz-harness path, unchanged) | **inconclusive**: needs a failing allocation; the allocation-failure check (advisory) reached only 4 allocations, none on that path |

Both wrong #572 fixes are now caught, so two of the five review findings (#571, #572) are caught
by a machine check; the correct #572 fixes and the csvsplit demo fix stay verified. Berry and jsmn still need the human review, which is why
"verified" on open bugs is reported as "verified, needs human review" and only toybox #572 is
ready to propose.
