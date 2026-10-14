# ARVO notes

Measured 2026-10-14 (kickoff E0 step 3.6) with `scripts/arvo_probe.py`. Per-case records: `cases/arvo/<id>.json`; raw reproducer output: `tests/fixtures/arvo/<id>.log`.

## What ARVO is and where things live

- Paper: Mei et al., "ARVO: Atlas of Reproducible Vulnerabilities for Open-Source Software", EuroS&P 2026. Code: https://github.com/n132/ARVO · metadata: https://github.com/n132/ARVO-Meta (both **BSD-2-Clause**).
- Metadata DB: `arvo.db` (SQLite, 162,656,256 B) from the ARVO-Meta release `v3.0.0` (2025-10-23). Kept at `~/.cache/leakproof/arvo/arvo.db`, not in the repo. Table `arvo`: `localId, project, reproduced, reproducer_vul, reproducer_fix, patch_located, patch_url, verified, fuzz_target, fuzz_engine, sanitizer, crash_type, crash_output, severity, report, fix_commit, language, repo_addr, submodule_bug`.
- 6,138 records, all `reproduced=1`, all `patch_located=1`, **all `verified=0`** (the column is unused). `language`: 744 `c`, 5,394 `c++` (that is the OSS-Fuzz project language, not the language of the buggy file). `sanitizer`: 4,293 asan, 1,293 msan, 552 ubsan.
- `localId` is the OSS-Fuzz issue id (now `https://issues.oss-fuzz.com/issues/<id>`). The README example `25402` is **not** in the v3.0.0 DB; ids range 40,096,184 – 438,309,779.

## Image naming (verified)

- `n132/arvo:<localId>-vul` — vulnerable source + built harness + PoC.
- `n132/arvo:<localId>-fix` — same at the fix commit. Existence checked via `https://hub.docker.com/v2/repositories/n132/arvo/tags/<tag>` (no pull needed).
- `reproducer_vul` in the DB is literally `docker run --rm -it n132/arvo:<id>-vul arvo`.

## Inside a `-vul` image

| Thing | Where |
|---|---|
| Reproducer | `/bin/arvo` (bash). `arvo` = run harness on PoC; `arvo compile` = rebuild; `arvo run` = same as no args |
| Harness binary | `/out/<fuzz_target>` (plus `/out/llvm-symbolizer`) |
| Crash input (PoC) | `/tmp/poc` |
| Source | `/src/<project>`; build script `/src/build.sh`; fuzzer engines in `/src/{libfuzzer,aflplusplus,honggfuzz}` |
| Build entry | `/usr/local/bin/compile` (OSS-Fuzz base-builder), which appends sanitizer flags to `$CFLAGS`/`$CXXFLAGS` and runs `build.sh` |
| WORKDIR | **matters**: `build.sh` uses relative paths (md4c: `mkdir build; cd build; cmake ../`). md4c/sudo images set `/src/<project>`, lua sets `/src`. Running `arvo compile` from the wrong cwd fails with `CMake Error: The source directory "/src" does not appear to contain CMakeLists.txt.` Contree drops WORKDIR on import, so each case records `workdir` and the Runner passes it as `cwd`. |
| Baked env | `CC=clang CXX=clang++ CFLAGS="-O1 -fno-omit-frame-pointer -gline-tables-only -DFUZZING_BUILD_MODE_UNSAFE_FOR_PRODUCTION" SANITIZER=address OUT=/out SRC=/src` |
| Reproducer env | `/bin/arvo` exports OSS-Fuzz's `ASAN_OPTIONS` including **`detect_leaks=0`**, `detect_stack_use_after_return=1`, `strip_path_prefix=/workspace/`, plus `FUZZER_ARGS="-rss_limit_mb=2560 -timeout=25"` |

How to extract harness + PoC for our own pipeline: run from the `-vul` image with `save=True` (or `docker cp`) on `/out/<fuzz_target>` and `/tmp/poc`; for a rebuild we keep the whole image as the baseline and run `arvo compile` inside it.

## Rebuilding with our flags

`compile` honours `$CFLAGS`/`$CXXFLAGS` from the environment and appends `-fsanitize=address -fsanitize-address-use-after-scope -fsanitize=fuzzer-no-link`. So:

```bash
export CFLAGS="-O0 -gline-tables-only -DFUZZING_BUILD_MODE_UNSAFE_FOR_PRODUCTION"
export CXXFLAGS="$CFLAGS -stdlib=libc++"
cd <workdir> && arvo compile && arvo
```

All three cases reproduced the same crash kind and location after this `-O0` rebuild. Network was off for every run (`--network none`): neither `arvo` nor `arvo compile` needed the network for these three.

## Leaks: ARVO has none

No `crash_type` in the 6,138 records mentions leaks, and the reproducer runs with `detect_leaks=0`. **ARVO cannot supply CWE-401 cases.** Leak cases must come from elsewhere (Juliet; OSS-Fuzz "Memory leak" issues outside ARVO; re-running ARVO harnesses with `detect_leaks=1` to harvest incidental leaks — untested). Question for Samuel in `docs/HUMAN.md`.

## The label is not the crash

ARVO `crash_type` comes from the original OSS-Fuzz report. For lua `42508415` it says `Heap-use-after-free READ 1`, but the reproducer (and ARVO's own stored `crash_output`) reports `heap-buffer-overflow ... ltable.c:650:7 in luaH_newkey`. The gate and the eval must key on the **reproduced** report (our parser), and per-CWE tables must say which source the CWE came from.

ARVO's stored `crash_output` contains ANSI colour escapes; `parse_report` strips them.

## Selected E0 cases

| id | project | ARVO crash_type | reproduced (parsed) | CWE | location | workdir | pull (cold) | image on disk (content) | `arvo` | `arvo compile` | `-O0` rebuild | `-fix` on Hub |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 42493685 | md4c | Heap-buffer-overflow READ 1 | heap-buffer-overflow | CWE-122 | `src/md4c.c:5659` (`md_is_container_mark`) | /src/md4c | 54 s | 5.29 GB (1.37 GB) | 0.34 s | 18.7 s, reproduces | 18.9 s, reproduces | yes, 0.63 GB |
| 42508415 | lua | Heap-use-after-free READ 1 | **heap-buffer-overflow** | CWE-122 | `ltable.c:650` (`luaH_newkey`) | /src | ~55 s | 5.31 GB (1.38 GB) | 0.33 s | 53.7 s, reproduces | 51.9 s, reproduces | yes, 0.68 GB |
| 42492467 | sudo | Heap-double-free | double-free | CWE-415 | `plugins/sudoers/gram.y:1866` | /src/sudo | 55.7 s | 5.59 GB (1.56 GB) | 0.34 s | 53.4 s, reproduces | 42.0 s, reproduces | yes, 1.55 GB |

Compressed sizes on Docker Hub: 1.37 / 1.38 / 1.56 GB (`-vul`). Rebuilds ran with the Runner's default limits (2 CPUs, 4 GiB). Pull times are wall clock on this connection.

## Practical limits

- Disk: each `-vul` image is ~5.3–5.6 GB unpacked; Docker Desktop's data disk is on `C:` (26 GB free after E0). A 40–60 case eval cannot keep all images locally at once; plan pull → run → `docker rmi` per case, or run ARVO cases in Contree once approved (import once per case).
- Candidate shortlist (small C projects, asan, patch located): md4c (4), lua (4), jq (9), libucl (10), miniz (2), mosquitto (9), oniguruma (7), zstd (10), lcms (27), h3 (3), libyaml (1), sudo double frees (2), libdwarf double frees (2), libredwg double frees (10). Query in `scripts/arvo_probe.py` neighbourhood; selection for E1 is still open.

## Licensing

ARVO and ARVO-Meta are BSD-2-Clause. The images contain the upstream projects under their own licenses (md4c MIT, Lua MIT, sudo ISC-style). We redistribute nothing from the images: the repo stores only metadata, our parsed findings, and the reproducer's stderr (a few KB per case) as test fixtures.
