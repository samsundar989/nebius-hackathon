# `leakproof init` on the 10 hand-configured open-bugs projects

Review #8 order 4. For each project, `leakproof init <clone> --issue-text <issue>` drafted a
config (`scripts/init_eval.py draft`; Nemotron Nano read each issue once, $0.005 in total), and
the draft was prepared unchanged in the toolchain image (`scripts/init_eval.py check`, job 3856,
no model calls): does it build, and does its reproducer trip a sanitizer? Drafts and results are
in `runs/init_eval/` (not committed). Two earlier rounds (jobs 3854, 3855) found three
deterministic problems, fixed before this one: exec bits on generator scripts, flags in `$CC`
breaking toybox's own compiler check, and out-of-tree binaries under `build/`.

| project | detected | builds unchanged | reproducer | edits a person still makes |
|---|---|---|---|---|
| struct2json | nothing (no build file) | — | `./tests2j` (right program) | write the build line (the demo is compiled by hand) |
| berry | make | no: `readline/readline.h` missing | `./berry /tmp/poc` (right) | build without readline (`LIBS=…`) |
| mjs | make | no: the Makefile builds inside Docker | `./mjs_asan …` (reporter's binary name) | build line + a runner for the input |
| cNBT | make | no: `-Werror` vs clang 18's `-Wstrict-prototypes` | none in the issue | build line, reproducer (input given as hex was decoded) |
| tidy-html5 | CMake | **yes** | `build/repro` (the reporter's own C program) | add the reporter's program |
| toybox | make (`defconfig`) | **yes** | `./generated/unstripped/toybox patch < /tmp/poc` (right) | fix the input: Nano kept a `\"` escape and a newline was appended |
| libinjection | autotools | **yes** | `./repro` (reporter's program) | add the reporter's program |
| yajl | CMake | **yes** | `build/yajl_fuzzer …` (reporter's harness) | add a harness |
| nanosvg | CMake (header-only) | **yes** | none in the issue | add a program that loads the SVG |
| jsmn | make | **yes** | `./jsondump /tmp/poc` (example not built by `make`; input linked, not inline) | build the example, add the input |

**Result: 6 of 10 drafts build unchanged; 0 of 10 build and reproduce unchanged.** The reproducer
is the hard part: in 6 of 10 issues the reporter ran a program the project does not build (their
own harness or a test program), and in 3 the input is attached or linked rather than inline (we
never download it). `init` therefore saves the build-system work and leaves a marked `TODO` for
what the issue does not give; it does not turn an issue into a working config by itself.
