# Open bugs: triage (review #6 order 1)

Source: GitHub issue search on 2026-10-25 for open issues with an AddressSanitizer report
(`heap-buffer-overflow`, `stack-buffer-overflow`, `heap-use-after-free`), C projects, created
before 2026-09-25. Picked for a simple offline build (make, cmake or single files with the
toolchain image's clang 18) and a reproducer given **inline in the issue text**: we write it
ourselves and never download attachments from issue reporters. Projects in ARVO are excluded.

Upstream trees are shallow clones next to each config (`*/src/`, not committed); the HEAD
commit is recorded in `runs/open_bugs/reproduce.json`. Nothing is posted anywhere: any fix ready
to propose goes to Samuel (HUMAN.md), who decides whether to submit it under his name with an
AI-assistance disclosure.

| issue | defect | status | AI-contribution policy |
|---|---|---|---|
| [cesanta/mjs#324](https://github.com/cesanta/mjs/issues/324) | heap over-read in `skip_spaces_and_comments` | does not reproduce at HEAD: the cited `p->pos[1]` read sits behind `p->pos[0] == '/' &&`, which short-circuits on the terminator (code unchanged since the report) | none stated |
| [cesanta/mjs#322](https://github.com/cesanta/mjs/issues/322) | use-after-free in `mjs_next` (splice during for-in) | reproduces at HEAD (use-after-free, `mjs.c:11690`) → fix attempted (`cesanta_mjs/322`) | none stated |
| [libinjection/libinjection#90](https://github.com/libinjection/libinjection/issues/90) | over-read in `htmlencode_startswith` | does not reproduce at HEAD (the issue's 41 bytes run clean; several HTML5-tokenizer fixes landed since) | none stated |
| [landley/toybox#571](https://github.com/landley/toybox/issues/571) | heap overflow in `getopt` | reproduces at HEAD (`getopt.c:60`) → fix attempted | none stated |
| [landley/toybox#572](https://github.com/landley/toybox/issues/572) | heap overflow in `patch` | reproduces at HEAD (`patch.c:287`) → fix attempted | none stated |
| [berry-lang/berry#544](https://github.com/berry-lang/berry/issues/544) (lexer) | read past the lexer's end sentinel | does not reproduce at HEAD (likely fixed by upstream #546, "Harden VM and compiler against … hostile input") | none stated |
| [berry-lang/berry#544](https://github.com/berry-lang/berry/issues/544) (format) | `string.format` buffer overflow | reproduces at HEAD (stack-buffer-overflow, `be_strlib.c:690`) → fix attempted | none stated |
| [landley/toybox#579](https://github.com/landley/toybox/issues/579) | heap overflow in `sed` | reproduces at HEAD (`sed.c:753`); excluded: open PR #584 fixes it | — |
| [memononen/nanosvg#295](https://github.com/memononen/nanosvg/issues/295) | 1-byte over-read in `nsvg__parseNameValue` | reproduces at HEAD (`nanosvg.h:1951`); excluded: open PR #300 | AI_POLICY.md: AI-assisted PRs allowed only if a human reviews, submits and discloses; descriptions and discussion must not be AI-written |
| [memononen/nanosvg#288](https://github.com/memononen/nanosvg/issues/288) | same root cause as #295 | excluded: open PR #300 | as above |
| [lloyd/yajl#260](https://github.com/lloyd/yajl/issues/260) | over-read in `hexToDigit` | excluded: open PR #266 (our own driver did not trip it at HEAD either) | none stated |
| [DaveGamble/cJSON#1022](https://github.com/DaveGamble/cJSON/issues/1022) | use-after-free after `cJSONUtils_MergePatch` | excluded: the PoC keeps using `target` after `MergePatch` replaced it (the function returns the new root); API misuse, not a library defect | — |
| [libxmq/xmq#45](https://github.com/libxmq/xmq/issues/45) | stack overflow in a codepoint formatter | skipped: needs libxml2, not in the offline toolchain | — |
| [debevv/nanoMODBUS#120](https://github.com/debevv/nanoMODBUS/issues/120) | stack overflow in `handle_read_file_record` | skipped: needs a Modbus server harness; out of the time box | — |

Build notes: the clones must have LF line endings (`git -c core.autocrlf=false clone`), copied scripts need `chmod +x`, toybox's reproducer uses the unstripped binary, berry links without readline, and mjs builds with `-fno-sanitize=pointer-overflow` because UBSan flags NULL+0 pointer arithmetic in its garbage collector (`gc_mark_mbuf_pt`, `mjs.c:10791`) on every script, before any reported bug is reached; that is a separate, minor finding.

The nanosvg and yajl configs stay in the tree (they reproduce or not at HEAD, which is still a
data point), but no fix is attempted for issues with an open PR.
