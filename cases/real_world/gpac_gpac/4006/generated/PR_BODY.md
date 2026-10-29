Fixes #4006.

When a meta item is added from memory, `meta.c` copies its bytes into `infe->full_path`, allocated with exactly `data_len` bytes and not terminated. For a zero-length item, `DoWriteMeta()` in `isom_store.c` takes the `!data_len && full_path` branch and passes `full_path` to `gf_fopen()` as a file name, which reads past the allocation (the heap-buffer-overflow in `gf_fopen_ex` from the issue).

The fix allocates one more byte and terminates the copy. A zero-length in-memory item now gives an empty name, `gf_fopen()` fails, and the existing `if (!src) continue;` skips the item, as it does for any unreadable file. If you would rather write such items as empty items, I can change it.

<details><summary>AddressSanitizer, the issue's command on d958f94 (trimmed)</summary>

```
ERROR: AddressSanitizer: heap-buffer-overflow
READ of size 2 thread T0
    #0 fopen64
    #1 gf_fopen_ex utils/os_file.c:1721
    #2 DoWriteMeta isomedia/isom_store.c:900
    #3 DoInterleave isomedia/isom_store.c:1756
    #4 WriteInterleaved isomedia/isom_store.c:2053
0 bytes after 1-byte region (ASan's chunk for malloc(0))
allocated by thread T0 here:
    #0 malloc
    #1 gf_isom_add_meta_item_extended isomedia/meta.c:1772
    #2 gf_isom_add_meta_item_memory isomedia/meta.c:1806
    #3 mp4_mux_process_item filters/mux_isom.c:6068
```
</details>

**Tested** on d958f94 (Ubuntu 24.04, gcc 13.3, `./configure --enable-sanitizer --unittests`), the same commands on the unpatched and the patched tree:
- the issue's `MP4Box -decrypt drm_ctr.xml poc.mp4 -out out.mp4`: heap-buffer-overflow in `gf_fopen_ex` before the fix; exit 0, no sanitizer report after
- new unit test `meta_item_memory_zero_length` in `src/isomedia/unittests/ut_meta_item_memory.c` (`make unit_tests`): before the fix it aborts with the heap-buffer-overflow above, reached from `gf_isom_close()`; after the fix all 70 unit tests pass. It also checks that a 3-byte in-memory item round-trips through the written file
- testsuite `scripts/item.sh scripts/heif.sh scripts/items_pids.sh scripts/iff_crypt.sh scripts/encryption.sh scripts/decryption_selkey.sh` (`make_tests.sh -re -p=0`): 82 tests executed on each build, the same 79 pass on both; the same 3 (`meta`, `heif-unci`, `decryption-selkey`) fail on both because they need the external media, which I did not sync

**AI disclosure:** AI assistance was used to investigate the issue, prepare the patch and test, and draft this report (Leakproof, an AI repair agent I am building on NVIDIA Nemotron models; it keeps a patch only if it survives sanitizer checks on the reproducer and on inputs generated from it). The commands and results above were run locally. I reviewed the change and the test myself.
