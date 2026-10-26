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

toybox's README says the maintainer prefers patches **sent to the mailing list as a file
attachment** (the list holds messages from non-subscribers for moderation for a day or two), and
that its main repository is on Codeberg (https://codeberg.org/landley/toybox); GitHub is a mirror.
So, in order of preference:

1. **Mailing list.** Subscribe or post via https://lists.landley.net/mailman/listinfo/toybox.
   Write a short e-mail in your own words: the issue link
   (https://github.com/landley/toybox/issues/572), the one-line change, how you tested it, and the
   disclosure above. Attach `0001-patch.private.patch` (the gitignored copy with your identity).
   `generated/PR_BODY.md` has a draft of that text.
2. **Codeberg pull request**, which the maintainer applies with `git am`: fork
   https://codeberg.org/landley/toybox, apply the patch on a branch (`git am
   0001-patch.private.patch`), push, and open a pull request with the same text.

If the maintainer prefers to fix it differently, thank him and leave it there.
