# csvsplit — bring-your-own demo project

A ~100-line CSV field splitter written for this repo to show Leakproof on a project that is
not from a benchmark. It has one deliberate, realistic defect: a quoted field is copied into a
buffer sized for its content but not its terminator (`copy_quoted` in `src/csvsplit.c`), a
1-byte heap overflow that only quoted input reaches. Unquoted input, the unit tests and the
seed corpus run clean, so the gate can use all three.

```
uv run leakproof fix --config examples/csvsplit/leakproof.toml
```

`leakproof.toml` names the build (`make all`), the reproduction (`./csvsplit_fuzz /tmp/poc`
with `poc.csv`), the tests (`make test`) and the libFuzzer harness, which gives the gate its
differential corpus (`corpus/`), amplified re-fuzz and LeakSanitizer checks. Workers may edit
only `src/*.c` and `src/*.h`.

## Triage mode

`findings/` holds ten inputs — eight that trip the quoted-field overflow in different shapes and
two plain lines that do not — written by hand for this demo (not fuzzer output):

```
uv run leakproof batch --config examples/csvsplit/leakproof.toml --findings examples/csvsplit/findings
```

reproduces all ten on one baseline build, groups the crashes by signature (defect kind + top
in-project frames), fixes one representative per group with the full pipeline, and then runs
**every** member's input against the winning patch; a group counts as fixed only if all of them
are clean.
