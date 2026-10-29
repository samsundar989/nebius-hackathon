# Real-world targets (review #17 order 2, shortlist from review #18 B)

Still-open sanitizer issues in popular, active C/C++ projects, all **opened in October 2026**, after
the models' training data: a fix cannot be recalled, and none of the developers' fixes exists yet.
Checked 2026-10-29 00:30 CDT with the unauthenticated GitHub API: issue state, the timeline's
cross-references (no linked fix PR) and each project's AGENTS.md / AI policy / SECURITY.md. Nothing
has been posted anywhere.

The models see only the sanitizer finding from our own reproduction and the source files. They
never see the issue text: several issues include the reporter's suggested diff.

| # | target | opened | bug (reported) | reproducer | tests the gate runs | status |
|---|---|---|---|---|---|---|
| 1 | [assimp #6945](https://github.com/assimp/assimp/issues/6945) (13k★) | 2026-10-14 | LeakSanitizer leak in `STLImporter::LoadASCIIFile` | issue's STL + issue's `ReadFile` program | gtest `unit` (all suites) | config ready, probing |
| 2 | [LibreDWG #1450](https://github.com/LibreDWG/libredwg/issues/1450) (GNU) | 2026-10-14 | heap-buffer-overflow READ, `add_LTYPE_dashes` → `bit_wcs2cpy` | issue's DXF, `dwgwrite -y -I DXF` | `make -C test/unit-testing check` | config ready, probing |
| 3 | [LibreDWG #1439](https://github.com/LibreDWG/libredwg/issues/1439) | 2026-10-12 | heap-buffer-overflow WRITE, `_set_struct_field` (in_json.c) | issue's JSON, `dwgwrite -y -I JSON` | same | config ready (shares #2's build) |
| 4 | [gpac #4006](https://github.com/gpac/gpac/issues/4006) (3.3k★) | 2026-10-17 | heap-buffer-overflow READ, `gf_fopen_ex`/`DoWriteMeta` (meta.c) | attached poc.zip (SHA256 matches), `MP4Box -decrypt` | `make unit_tests` | config ready, probing |
| 5 | [quickjs-ng #1853](https://github.com/quickjs-ng/quickjs/issues/1853) | 2026-10-27 | heap-buffer-overflow, `JS_ReadFunctionTag` size overflow | issue's 65-byte input + `JS_ReadObject` program | `run-test262 -c tests.conf` | config ready, probing |
| 6 | [assimp #6927](https://github.com/assimp/assimp/issues/6927) | 2026-10-13 | heap-buffer-overflow, `glTFCommon::ParseDataURI` | issue's generator script | gtest `unit` | after 1–5 |
| 7 | [json-c #995](https://github.com/json-c/json-c/issues/995) | 2026-10-28 | heap-use-after-free after `json_pointer_set` | issue's poc.c | json-c tests | after 1–5; the PoC calls `json_object_put(val)` after `json_pointer_set` took ownership of `val`, so "refuse: the PoC misuses the API" may be the correct outcome |

**Dropped:** assimp #6929: [PR #6963](https://github.com/assimp/assimp/pull/6963) was merged 2026-10-25 (the issue is still open, the bug is fixed).
**Avoided** (review #18): OpenJPEG, HDF5, raylib, bellard/quickjs, issues with fix PRs, assimp's OSS-Fuzz mirror issues.

## Contribution rules that apply to any fix we send

- **assimp** ([AIToolPolicy.md](https://github.com/assimp/assimp/blob/master/AIToolPolicy.md), AGENTS.md): AI tools allowed with a **human in the loop**: Samuel reads and understands every line, can answer review questions, labels it (`Assisted-by:` trailer). AI may not fix `good first issue` issues (#6945 is not labelled). PR on GitHub. #6927 is labelled "Security Risk"; SECURITY.md names a private e-mail route.
- **LibreDWG** (AGENTS.md, CONTRIBUTING, SECURITY.md): minimal, root-cause fixes with a test where feasible; `make check`; clang-format only changed lines; no generated files; ChangeLog-style message. SECURITY.md prefers GitHub security advisories for vulnerabilities; #1450 and #1439 are already public issues, so a PR referencing them adds no disclosure.
- **gpac** (AGENTS.md, `.agents/skills/gpac-patching`): reproduce on current master, smallest complete fix, a **regression test** in `src/*/unittests/` or the testsuite, a PR body with fixed headings; AI use must be disclosed.
- **quickjs-ng** (SECURITY.md): bytecode loading is out of scope for security reports; a plain bug-fix PR.
- **json-c**: a PR, if the analysis finds a library defect at all.

## Budget

≤ $5 for the whole campaign (main ledger cap $19, review #17). Probes (build + reproduce + tests) run first at $0; `leakproof fix --adversary auto` only on a target whose probe passes.
