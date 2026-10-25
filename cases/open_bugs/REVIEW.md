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
