AddressSanitizer reports a heap-buffer-overflow in gf_fopen_ex()
(src/utils/os_file.c:1721).

The change, in meta.c:

    -				infe->full_path = (char *)gf_malloc(sizeof(char) * data_len);
    +				infe->full_path = (char *)gf_malloc(sizeof(char) * (data_len + 1));
    +				infe->full_path[data_len] = '\0';

Tested: the issue's `MP4Box -decrypt` reproducer runs clean under AddressSanitizer (gpac's --enable-sanitizer build); 3 truncated variants of the PoC also run clean. gpac's unit tests and testsuite were NOT run, and the regression test gpac asks for is not written yet. Behaviour note: a zero-length in-memory item now reaches gf_fopen(""), which fails, so the item is skipped at write time instead of over-reading.

This patch was developed with Leakproof, an AI repair agent; its candidate passed sanitizer-based checks. TODO before sending: review the change, run the testsuite, add a unit test in src/isomedia/unittests/.

Fixes #4006.
