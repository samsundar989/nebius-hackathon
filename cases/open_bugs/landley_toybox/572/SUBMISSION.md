# toybox #572: submission package (for Samuel; nothing has been posted)

Issue: https://github.com/landley/toybox/issues/572 — heap-buffer-overflow in `patch`
(`unquote_file`, `toys/posix/patch.c:287`), open since 2025-10-03, no PR. Upstream HEAD: `6a0c0ef`.

## The patch

`0001-patch-reject-a-quoted-filename-that-ends-inside-an-escape.patch` (this directory),
`git format-patch` form, author set to your git identity (the committed copy says `<your git identity>`; a local, gitignored `0001-patch.private.patch` carries yours;
change it with `git am` and `git commit --amend --reset-author` if you use another). It is the
one-line fix:

```diff
-    if (!s[1]) error_exit("bad %s", filename);
+    if (!*s || !s[1]) error_exit("bad %s", filename);
```

Why: `unquote_file()` checks `s[1]` at the top of its loop, but an escape sequence can consume the
last character and leave `s` on the terminator; the next iteration reads past the end of the string
and keeps writing past the buffer. Stopping at the terminator as well fixes it on every path (plain
character, `\` escape, octal escape).

Leakproof's own verified candidate (H2·w1, `proposed.diff`) is a correct 26-line pre-scan; the
one-liner is the same fix with no change to how the buffer is sized, so it is the one to send.

## Evidence (`runs/open_bugs_572_manual/gate.json`, gate run with no model calls)

| check | one-liner | H2·w1 |
|---|---|---|
| the issue's reproducer under ASan+UBSan (unpatched: heap-buffer-overflow at `patch.c:287`) | clean | clean |
| compiled into the binary under test (hash of `generated/unstripped/toybox`) | changed | changed |
| toybox's own `patch` tests (`tests/patch.test`, 13 tests, ASan build) | 13/13 pass (13/13 on the unpatched build) | 13/13 pass |
| corpus differential, amplified re-fuzz, leak check | not run: no fuzz harness for toybox in our setup | not run |

Before sending, run `make test_patch` (or `scripts/test.sh patch`) in your own build. Note: built
with UBSan, 12 of the 13 tests fail at HEAD because UBSan reports an unrelated issue in
`lib/xwrap.c:428` into their output; that is pre-existing and separate from this fix.

## Commit message (in the patch)

```
patch: reject a quoted filename that ends inside an escape

unquote_file() checks s[1] at the top of its loop, but an escape sequence can
consume the last character and leave s on the terminator. The next iteration
then reads past the end of the string and keeps writing past the buffer
(heap-buffer-overflow, toys/posix/patch.c:287). Stop at the terminator too.

Fixes #572.
```

## AI-assistance disclosure (put it in the PR or e-mail text)

> This fix was developed with Leakproof, an AI repair agent: its sanitizer-verified patch was reduced
> to this one line during an AI-assisted review. I reviewed the change and ran toybox's patch tests myself.

The repository states no AI-contribution policy. Check the project's README for how it prefers to
receive patches, and keep the description short and in your own words.

## Send it in 5 minutes (only after reading the patch and running the tests; nothing here has been run)

A ready PR description is in `generated/PR_BODY.md` (what changed, how it was tested, the
disclosure); replace its first paragraph with the "Why" above if you prefer the reviewed wording.
toybox also takes patches on its mailing list (see the project README); if you go that way, send
the patch file with `git send-email` instead.

**GitHub, in the browser**
1. Open https://github.com/landley/toybox and click **Fork**.
2. In your fork, open `toys/posix/patch.c`, click the pencil (Edit), change the line shown above,
   and commit it to a new branch (for example `leakproof-fix-572`).
3. Click **Compare & pull request**; title: `patch: reject a quoted filename that ends inside an
   escape`; paste the PR description.

**Command line** (needs `gh`, logged in)
```
gh repo fork landley/toybox --clone && cd toybox
git checkout -b leakproof-fix-572
git am /path/to/0001-patch-private.patch   # the gitignored copy with your identity
git push -u origin leakproof-fix-572
gh pr create --repo landley/toybox --title "patch: reject a quoted filename that ends inside an escape" --body-file /path/to/generated/PR_BODY.md
```

If the maintainer prefers to fix it differently, thank them and close the PR.
