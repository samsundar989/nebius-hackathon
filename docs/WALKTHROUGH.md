# Walkthrough: from a crash to a patch a maintainer can review

The judge's "try it" path, on `examples/csvsplit` (a CSV splitter with a one-byte heap overflow).
Every output below is real, from 2026-10-26 (run `runs/walkthrough`, $0.0157 of model spend,
224 s), trimmed where marked. You need Docker, Python 3.12 with `uv`, and a Nebius Token Factory
key in `.env` (`cp .env.example .env`, then fill in `NEBIUS_API_KEY` and `NEBIUS_PROJECT_ID`).

```
uv sync
uv run leakproof doctor --config examples/csvsplit/leakproof.toml
```

`doctor` prints one PASS / WARN / FAIL line per check (Docker engine, the toolchain image, the key
accepted by Token Factory without printing it, Sandboxes, budget and ledger cap, the config) and
the fix for each failure, for example the `docker build` command when the image is missing.

## 1. `leakproof init`: draft a config

```
uv run leakproof init examples/csvsplit --out examples/csvsplit/leakproof.draft.toml
```

```toml
# Drafted by `leakproof init` (make); check it with `leakproof fix`.
[project]
name = "csvsplit"
src = "."
build = '''grep -rlI --exclude-dir=.git '^#!' . | xargs -r chmod +x ; make -j4'''
# TODO reproduce = '''./your-binary /tmp/poc'''  # must trip a sanitizer
test = '''make test'''
editable = ["src/*.c", "src/*.h"]
```

It found the Makefile, the test target and the source directory. The reproducer is a `TODO`:
there was no issue text to read (`--issue-text bug.md` lets Nemotron 3 Nano pull the reporter's
command and input from a bug report). The finished config, `examples/csvsplit/leakproof.toml`,
adds the reproducer and the fuzz harness:

```toml
[project]
name = "csvsplit"
src = "."
build = "make all"
reproduce = "./csvsplit_fuzz /tmp/poc"
test = "make test"
harness = "csvsplit_fuzz"
poc = "poc.csv"
editable = ["src/*.c", "src/*.h"]
```

How well drafts do on real projects: [cases/open_bugs/INIT_EVAL.md](../cases/open_bugs/INIT_EVAL.md)
(6 of 10 build unchanged; the reproducer is what you write).

## 2. `leakproof fix`: plan, patch, gate

```
uv run leakproof fix --config examples/csvsplit/leakproof.toml --adversary auto
```

```
verdict: verified   $0.0157   224.06 s
  H1 w0: verified                             reviewer notes: root_cause
  H1 w1: verified                             reviewer notes: -
  H1 w2: verified                             reviewer notes: root_cause
  H1 w3: verified                             reviewer notes: root_cause
VERIFIED: evidence medium: project tests ran; harness prints nothing the differential can compare
winning diff:
--- a/src/csvsplit/src/csvsplit.c
+++ b/src/csvsplit/src/csvsplit.c
@@ -19,7 +19,7 @@
     size_t inner = n >= 2 ? n - 2 : 0;
-    char *field = malloc(inner); /* room for the content */
+    char *field = malloc(inner + 1); /* room for the content */
record: runs/walkthrough/project_csvsplit.json
```

Nemotron 3 Ultra found the root cause (the allocation has no room for the terminator), four
Nemotron 3.5 Lightning workers each wrote a patch, and the gate, in its own process with the
network off, verified all four. `--adversary auto` resolved to **off** here, because csvsplit has
project tests and a fuzz harness; on a project with neither, Nemotron 3 Super would attack each
verified candidate with up to 8 inputs (`--adversary super` forces it: the
[earlier run with it on](../examples/csvsplit/submission_example/SUBMISSION.md) shows the row
"inputs a Nemotron model wrote to break this patch: pass").

## 3. The evidence bundle

```
uv run python scripts/render_bundle.py walkthrough --all --out bundle
```

```
# csvsplit: verified
- Cost: $0.0157 Nemotron 3 Ultra $0.0123 · Nemotron 3.5 Lightning $0.0033

| check        | result | evidence                                                         |
|--------------|--------|------------------------------------------------------------------|
| patched      | pass   | no sanitizer report, exit 0                                      |
| tests        | pass   | ./test_csvsplit all passed                                       |
| differential | pass   | 5 inputs; exit codes and stdout identical                        |
| refuzz       | pass   | 11 amplified variants clean; libFuzzer 90s, 117,367,541 runs     |
| safe_fix     | pass   | 5 inputs under LeakSanitizer: no new leak/UAF/double free        |
(trimmed: unpatched_trips, diff_scope, build, compiled; the other verified candidate)
```

Every check is listed with what it ran. A refused case leads with the first check that failed
and why: see [the jq refusal](bundles/42530604.md).

## 4. `leakproof package`: what a maintainer receives

```
uv run leakproof package runs/walkthrough/project_csvsplit.json --out submission
```

```
wrote submission/SUBMISSION.md
wrote submission/0001-csvsplit-fix-heap-buffer-overflow-in-copy-quoted.patch
```

The patch is `git format-patch` form (`git am` applies it); its message describes the diff, not
the plan:

```
Subject: [PATCH] csvsplit: fix heap-buffer-overflow in copy_quoted()

AddressSanitizer reports a heap-buffer-overflow in copy_quoted()
(src/csvsplit.c:33).

The change, in src/csvsplit.c:

    -    char *field = malloc(inner); /* room for the content */
    +    char *field = malloc(inner + 1); /* room for the content */
```

`SUBMISSION.md` carries the evidence table (every check, including the ones that did not run and
why), the planner's analysis in its own section (written before the fix, so check it against the
diff), an AI-assistance note and a "Before sending" checklist. The author is a placeholder until
`--author` or `git commit --amend --reset-author`.

## 5. What to do with it

1. Read the diff and the planner's analysis; add a sentence on *why* to the commit message.
2. Run the project's tests in your own build.
3. Check the project's contribution guide and AI-contribution policy.
4. Send it, in your own words, with the disclosure.

A real case: [toybox #572](../cases/open_bugs/landley_toybox/572/generated/SUBMISSION.md), an
open upstream bug, packaged the same way and waiting for a human decision. In CI the same steps
run after a failed fuzzing job (`.github/workflows/leakproof-fix.yml`), and the patch and
SUBMISSION.md are uploaded with the evidence.
