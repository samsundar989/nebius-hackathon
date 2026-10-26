AddressSanitizer reports a heap-buffer-overflow in next() (elk.c:535).

The change, in elk.c:

    -      if (buf[0] == buf[js->tlen]) js->tok = TOK_STRING, js->tlen++;
    +      if (js->toff + js->tlen < js->clen && buf[0] == buf[js->tlen]) js->tok = TOK_STRING, js->tlen++;

Not fixed here: numbers are still parsed with strtod past the slice length (the issue's first case).

Tested: the reproducer from the issue runs clean under AddressSanitizer/UBSan; the project's own tests could not be used (suite fails on the unpatched baseline too).

This patch was developed with Leakproof, an AI repair agent; its candidate passed sanitizer-based checks. I reviewed the change and ran the project's tests myself.

Part of #82.
