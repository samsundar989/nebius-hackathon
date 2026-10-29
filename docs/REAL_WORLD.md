# Real world: still-open bugs in popular projects (October 2026)

**Why these bugs.** ARVO's developer fixes have been public for years, so a model may have seen
them in training. These issues were all **opened in October 2026, after the models' training
data**, and none had a fix anywhere when we ran: a fix cannot be recalled, only made. The models
saw only our own sanitizer reproduction and the source; never the issue text (several include
the reporter's suggested diff).

Targets, policies and how each was checked: [cases/real_world/TARGETS.md](../cases/real_world/TARGETS.md).
Machine-readable: [cases/real_world/funnel.json](../cases/real_world/funnel.json).

## Funnel

| | count |
|---|---|
| shortlisted issues (≥ 1.6k★, active, sanitizer report + reproducer, no fix PR) | 8 |
| already fixed upstream when re-checked (issue left open) | 3: assimp #6929, LibreDWG #1450, #1439 |
| reproduced at upstream HEAD and attempted | 5 |
| verified by the gate | 2: gpac #4006, assimp #6927 |
| after review (Claude, outside the pipeline) | **1 correct fix** (gpac #4006, minimal; gpac shipped an equivalent fix on Oct 29 before ours was sent) and **1 partial fix** (assimp #6927), both packaged; nothing sent |

Model spend for the campaign: $1.27 (ledger: every `rw_*` run and its gate adversary calls), including runs that exposed tooling bugs.

## Per issue

**gpac #4006: heap-buffer-overflow READ via an unterminated meta item path (3.3k★). Verified, correct; gpac then fixed it the same way.**
`gf_isom_add_meta_item_extended` copies an in-memory item into `full_path` with exactly `data_len`
bytes and no terminator; when `data_len` is 0, the writer treats `full_path` as a file name and
`gf_fopen` reads past the 1-byte allocation. 3 of 4 candidates verified, all the same fix:
allocate `data_len + 1` and NUL-terminate. Review (Claude, outside the pipeline): **correct and minimal** for the reported
defect. A zero-length in-memory item now reaches `gf_fopen("")`, fails and is skipped at write time
instead of over-reading. The gate's evidence was weak by our own definition (gpac's unit tests did
not run in the gate's build; the 148 KB PoC yields only 3 generated inputs), so on Oct 29 we did the
three things gpac's patching rules ask for, with gpac's own `--enable-sanitizer --unittests` build
on `d958f94` ([validate.sh](../cases/real_world/gpac_gpac/4006/validate.sh),
[RESULTS](../cases/real_world/gpac_gpac/4006/validation/RESULTS.txt)): the issue's command crashes
unpatched and is clean patched; a new public-API unit test aborts under ASan unpatched and passes
patched (70/70 unit tests); 6 affected testsuite scripts give the same 79/82 on both builds (the 3
failures need external media). **Before we sent it, gpac fixed the bug itself:**
[3f05654](https://github.com/gpac/gpac/commit/3f056542b3) (Oct 29, "fixes #4006") changes
`if (data)` to `if (data && data_len)`, so a zero-length item never gets a `full_path`. Same path,
same outcome as ours (no over-read, the item is skipped); the maintainer's fix agrees with the
review. Nothing was sent ([package](../cases/real_world/gpac_gpac/4006/generated/SUBMISSION.md);
QUESTION 0023). $0.14. One run exposed a Leakproof bug: on a CRLF checkout the edit step
rewrote whole files (a 2-line fix became a 2,249-line diff); fixed, and the clean patch was re-gated
without a model call (`runs/rw_gpac_4006_clean`).


**assimp #6927: heap-buffer-overflow, glTF data URI (13k★, labelled Security Risk). Verified, partial.**
`glTFCommon::Util::ParseDataURI` stores the data offset in a signed `char`; a URI longer than 127
bytes wraps it and `glTF2::Buffer::Read` copies from before the buffer. 3 of 4 candidates verified
(assimp's 720 gtest tests ran, 233 inputs generated from the PoC re-run unpatched and patched).
The winner bounds-checks the copy the PoC reaches. Review (Claude, outside the pipeline): correct but **partial**: the
signed-char offset and its other callers (base64 branch, image URIs, the glTF 1 importer) remain.
Packaged as "Part of #6927" with that said plainly ([package](../cases/real_world/assimp_assimp/6927/generated/SUBMISSION.md),
applies to upstream `a2a586d`); QUESTION 0022, default not sent. One more detail the gate showed:
the two patches that put the same check before the base64 branch were rejected by the
differential, because on 10 generated inputs the unpatched importer silently read wrapped data
without a sanitizer report and the patch changed that output. The gate is conservative there.
The first run's three built candidates had been rejected as out of scope because our gate did not
treat `.inl` as a source file; fixed, and those three re-gated without a model call
(`runs/rw_assimp_6927_regate`).
A third run on Oct 29 aimed at the root cause (`--notes`: Claude Code's review of the partial fix,
no gate inputs; Ultra + one repair round; $0.21, `runs/rw_assimp_6927_r3`) **did not verify**, and
it exposed a Leakproof limitation: the models are shown the files on the crash stack, and
`ParseDataURI`'s `glTFCommon.cpp` is not on it (the function returns before the crash), so it was
never shown. Round 1's plan therefore guarded the caller again (4 candidates, all refused by the
differential: output changed on 10 of 203 generated inputs); round 2's plan named the root cause
but could point only at the header, and no edit applied. Fix for later: let a planner ask for a
file that is not on the stack.

**quickjs-ng #1853: heap-buffer-overflow in bytecode loading (4.0k★). No fix: the gate refused three silencers.**
Both candidates that built "fixed" the crash by clamping the free loop to the allocation's usable
size: the sanitizer went quiet on the PoC, and quickjs's own test suite then failed with new
sanitizer reports, so the gate refused both (`silenced_only`). The size computation that overflows
is untouched by either. This is "sanitizer silent ≠ fixed" on a bug opened two days earlier.
$0.41, the costliest run: quickjs.c is 2.1 MB and Ultra's plan read large windows of it. A second run with the cheaper Super planner ($0.11) produced the sharpest
case of the campaign: a patch that stops freeing the argument entries passed the PoC **and all of
quickjs's own tests** (0/120 errors), and re-fuzzing then hit the same overflow on 2 of 202
generated inputs, so the gate refused it. Both planners blamed the `vardefs` loop; the
issue's overflow is in the `cpool_count` size computation.

**assimp #6945: LeakSanitizer leak in the STL importer. No fix.**
The one candidate that built deleted the meshes and nodes on an early-EOF path and kept using
them; the gate caught the new use-after-free. A second run with a repair round produced only
build failures: the workers attempted `unique_ptr` refactors of a 400-line C++ function.

**json-c #995: a control.** The PoC calls `json_object_put(val)` after `json_pointer_set` took
ownership of `val`, which `json_pointer.h` documents. Nothing shipped, which is the right
outcome, but for the wrong reason: every worker edit failed to apply, and Ultra's root cause blamed
json-c's own refcounting. Leakproof has no "the reproducer misuses the API" verdict; a person
reading the header does.

**Dropped: already fixed upstream.** assimp #6929 (PR #6963, Oct 25), LibreDWG #1450
(`7b3144b3`, Oct 28) and #1439 (`bbaec638`, Oct 27): the issues are still open but the bugs are
gone at HEAD. For #1450 our reproduction at HEAD shows only an unrelated leak, so we did not fix
that instead.

## What this says about Leakproof

- The gate did its job on real, new bugs. Of the 14 candidate patches that built: 7 verified
  (3 on gpac, one correct fix; 4 the same narrow check on assimp #6927, partial on review), 3 refused because they changed
  the program's output on generated inputs (the assimp variants above), 3 refused as quickjs silencers (two broke its tests; one passed them
  and was caught by re-fuzzing), 1 refused for introducing a use-after-free. It verified nothing that is
  wrong; the review outside the pipeline still had the last word ("partial").
- The workers are the weak link on large C++ files: most attempts failed to apply or to build.
- Real-world setup cost more effort than the model calls: Windows line endings and executable
  bits, CRLF sources, autotools needing `.git`, a 2.1 MB source file, a shared-library ASan link. Each became a
  fix in the product (`leakproof doctor`, `scripts/probe_case.py`, the per-file size limit, `.inl`
  support, GoogleTest result parsing).
