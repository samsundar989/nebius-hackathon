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

## Round 2 (review #7 order 5)

Same rules: open, public, reproducer written from the issue text, no open fix PR, never post.

| issue | defect | status | AI policy |
|---|---|---|---|
| [chmod222/cNBT#28](https://github.com/chmod222/cNBT/issues/28) (bug 1) | leak in `parse_named_tag` (unchecked `read_string` failure) | reproduces at HEAD (`nbt_parsing.c:182`) → fix attempted (`chmod222_cNBT/28_leak`) | none stated |
| [chmod222/cNBT#28](https://github.com/chmod222/cNBT/issues/28) (bug 2) | unbounded length in `read_int_array` | not a sanitizer trip at HEAD: libFuzzer stops the oversized `malloc` first (exit 71); a denial-of-service shape the gate does not judge | none stated |
| [htacg/tidy-html5#1177](https://github.com/htacg/tidy-html5/issues/1177) | `prvTidynewStack` allocations never freed | reproduces at HEAD (leak, `alloc.c:64`) → fix attempted | none stated |
| [zserge/jsmn#249](https://github.com/zserge/jsmn/issues/249) | out-of-bounds read in `example/jsondump.c` | reproduces at HEAD (`jsondump.c:34`) → fix attempted (PR #250 was closed unmerged) | none stated |
| [armink/struct2json#38](https://github.com/armink/struct2json/issues/38) | leak in the demo's `s2j_test2()` | demo needs `-Wno-error=int-conversion` with clang 18; reproduce re-run pending | none stated |
| [uclouvain/openjpeg#1641](https://github.com/uclouvain/openjpeg/issues/1641), [#1642](https://github.com/uclouvain/openjpeg/issues/1642) | `-OutFor` stack overflows | excluded: open PRs #1664, #1653/#1665 | — |
| [lloyd/yajl#261](https://github.com/lloyd/yajl/issues/261) | leak in `yajl_tree_parse` on failure | excluded: open PR #264 | — |
| [liblouis/liblouis#2096](https://github.com/liblouis/liblouis/issues/2096) | `typebuf` sized by caller's `outlen` | excluded: open PR #2104 (and the PoC passes a length larger than its buffer) | — |
| [liblouis/liblouis#2094](https://github.com/liblouis/liblouis/issues/2094) | heap overflow | excluded: the "reproducer" is a template with placeholder bytes | — |
| [madler/zlib#1299](https://github.com/madler/zlib/issues/1299), [rxi/fe#34](https://github.com/rxi/fe/issues/34), [OpenDMARC#441](https://github.com/trusteddomainproject/OpenDMARC/issues/441), [vincenthz/libjson#31](https://github.com/vincenthz/libjson/issues/31), [antirez/gguf-tools#25](https://github.com/antirez/gguf-tools/issues/25), [cesanta/mjs#104/#108/#158/#167/#170](https://github.com/cesanta/mjs/issues) | various | excluded: the reproducer is an attachment, a crafted binary, or a link to another repository (not downloaded) | — |
| [cesanta/elk#81](https://github.com/cesanta/elk/issues/81) | missing `nargs` check in the ESP32 example's `delay()` | skipped: the code is an Arduino example the offline toolchain does not build | — |
| [nothings/stb#1860](https://github.com/nothings/stb/issues/1860) | 16-bit PNG conversion overflow | skipped: needs a 23171×23171 PNG and attachments | — |
