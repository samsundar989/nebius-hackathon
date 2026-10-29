AddressSanitizer reports a global-buffer-overflow in utf8_decode()
(utf8.h:37).

The change is in utf8.h (+12/-0), so the reported access no longer
happens.

Not fixed here: overlong encodings, surrogates and non-continuation bytes are still accepted (the issue's other requests).

Tested: the reproducer from the issue runs clean under AddressSanitizer/UBSan; the project's own tests could not be used (no runnable project test suite in the image); 1 input(s) Nemotron Super wrote to break the patch found nothing attributable to it.

This patch was developed with Leakproof, an AI repair agent (Nemotron models on Nebius Token Factory); its candidate passed sanitizer-based checks. I reviewed the change myself.

Part of #1.
