AddressSanitizer reports a heap-buffer-overflow in next() (elk.c:535).

The change is in elk.c (+1/-1), so the reported access no longer
happens.

Not fixed here: numbers are still parsed with strtod past the slice length (the issue's first case).

Tested: the reproducer from the issue runs clean under AddressSanitizer/UBSan; the project's own tests could not be used (suite fails on the unpatched baseline too).

This patch was developed with Leakproof, an AI repair agent (Nemotron models on Nebius Token Factory); its candidate passed sanitizer-based checks. I reviewed the change myself.

Part of #82.
