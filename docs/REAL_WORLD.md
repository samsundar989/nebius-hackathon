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
| reproduced at upstream HEAD and attempted | 4 (gpac #4006 still in setup, see below) |
| verified by the gate | 1: assimp #6927 |
| after hand review | **1 partial (defensive) fix**, packaged; 0 complete |

Model spend for the campaign: $0.84 (ledger: every `rw_*` run and its gate adversary calls), including runs that exposed tooling bugs.

## Per issue

**assimp #6927: heap-buffer-overflow, glTF data URI (13k★, labelled Security Risk). Verified, partial.**
`glTFCommon::Util::ParseDataURI` stores the data offset in a signed `char`; a URI longer than 127
bytes wraps it and `glTF2::Buffer::Read` copies from before the buffer. 3 of 4 candidates verified
(assimp's 720 gtest tests ran, 233 inputs generated from the PoC re-run unpatched and patched).
The winner bounds-checks the copy the PoC reaches. Hand review: correct but **partial**: the
signed-char offset and its other callers (base64 branch, image URIs, the glTF 1 importer) remain.
Packaged as "Part of #6927" with that said plainly ([package](../cases/real_world/assimp_assimp/6927/generated/SUBMISSION.md),
applies to upstream `a2a586d`); QUESTION 0022, default not sent. One more detail the gate showed:
the two patches that put the same check before the base64 branch were rejected by the
differential, because on 10 generated inputs the unpatched importer silently read wrapped data
without a sanitizer report and the patch changed that output. The gate is conservative there.
The first run's three built candidates had been rejected as out of scope because our gate did not
treat `.inl` as a source file; fixed, and those three re-gated without a model call
(`runs/rw_assimp_6927_regate`).

**quickjs-ng #1853: heap-buffer-overflow in bytecode loading (4.0k★). No fix: the gate refused two silencers.**
Both candidates that built "fixed" the crash by clamping the free loop to the allocation's usable
size: the sanitizer went quiet on the PoC, and quickjs's own test suite then failed with new
sanitizer reports, so the gate refused both (`silenced_only`). The size computation that overflows
is untouched by either. This is "sanitizer silent ≠ fixed" on a bug opened two days earlier.
$0.41, the costliest run: quickjs.c is 2.1 MB and Ultra's plan read large windows of it.

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

- The gate did its job on real, new bugs. Of the 10 candidate patches that built: 4 verified
  (all the same narrow check on assimp #6927; partial on review), 3 refused because they changed
  the program's output on generated inputs (the assimp variants above), 2 refused as silencers that
  broke quickjs's tests, 1 refused for introducing a use-after-free. It verified nothing that is
  wrong; hand review still had the last word ("partial").
- The workers are the weak link on large C++ files: most attempts failed to apply or to build.
- Real-world setup cost more effort than the model calls: Windows line endings and executable
  bits, autotools needing `.git`, a 2.1 MB source file, a shared-library ASan link. Each became a
  fix in the product (`leakproof doctor`, `scripts/probe_case.py`, the per-file size limit, `.inl`
  support, GoogleTest result parsing).
