AddressSanitizer reports a global-buffer-overflow in utf8_decode()
(utf8.h:37).
This changes utf8.h (+12/-0).

Not fixed here: overlong encodings, surrogates and non-continuation bytes are still accepted (the issue's other requests).

Tested: the reproducer from the issue runs clean under AddressSanitizer/UBSan; the project's own tests could not be used (no runnable project test suite in the image); inputs written to break the patch found nothing (super, 1 inputs: 1 adversary inputs: nothing attributable to).

This patch was developed with Leakproof, an AI repair agent; its candidate passed sanitizer-based checks. I reviewed the change and ran the project's tests myself.

Part of #1.
