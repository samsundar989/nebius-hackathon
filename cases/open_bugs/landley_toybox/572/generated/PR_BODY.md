AddressSanitizer reports a heap-buffer-overflow in unquote_file()
(toys/posix/patch.c:287).

The change, in toys/posix/patch.c:

    -    if (!s[1]) error_exit("bad %s", filename);
    +    if (!*s || !s[1]) error_exit("bad %s", filename);

Tested: the reproducer from the issue runs clean under AddressSanitizer/UBSan; the project's own tests pass.

This patch was developed with Leakproof, an AI repair agent; its candidate passed sanitizer-based checks. I reviewed the change and ran the project's tests myself.

Fixes #572.
