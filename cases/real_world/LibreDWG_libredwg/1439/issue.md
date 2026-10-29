# Heap-buffer-overflow write in JSON import of LWPOLYLINE `widths` (_set_struct_field treats pointer field as inline)

https://github.com/LibreDWG/libredwg/issues/1439 (opened 2026-10-12T08:38:01Z)

## Summary

`dwgwrite` on JSON whose `LWPOLYLINE` has `"widths": {"start": .., "end": ..}` writes 8 bytes past the 128-byte entity allocation (ASan: heap-buffer-overflow, WRITE of size 8). The written value is the parsed JSON double, and the `widths` pointer itself is overwritten with an attacker-controlled value.

Sibling of 1a12d14e ("Fix ossfuzz 42533395 …"), which made the two dotted-key (`a.b`) branches of `_set_struct_field` dereference pointer-typed fields and allocate the subclass struct when NULL. The plain-key branch of the embedded "subclass structs" block (`src/in_json.c:2918`) was left unchanged and still uses the address of the pointer field as the struct buffer. Not a dup of #1258 (double-offset, fixed in a0b2cae6, a non-pointer case).

## Version

master ee49c38f (2026-10-11). CMake Debug + `-fsanitize=address`, target `dwgwrite`.

## Steps to reproduce

Save the following as `poc.json`:
```json
{
  "FILEHEADER": { "version": "AC1015" },
  "OBJECTS": [
    { "entity": "LWPOLYLINE", "index": 0, "type": 77, "handle": [0,2,450],
      "widths": { "start": 1.0, "end": 2.0 } }
  ]
}
```
```
dwgwrite -y -o out.dwg poc.json
```
```
==ERROR: AddressSanitizer: heap-buffer-overflow ... WRITE of size 8
    #4 _set_struct_field  src/in_json.c:2221
    #5 _set_struct_field  src/in_json.c:2919
    #6 json_OBJECTS       src/in_json.c:3761
0x…0c0 is located 0 bytes after 128-byte region allocated at in_json.c:3447
```

## Root cause

`Dwg_Entity_LWPOLYLINE` ends with `Dwg_LWPOLYLINE_width* widths;` (a pointer, the last field). For a JSON object on this field the plain-key branch computes `off = &_obj[f->offset]`, the address of the pointer slot, not an allocated struct. `start` is then written into the pointer slot and `end` at `off+8`, i.e. exactly at `sizeof(entity)`, which is one 8-byte write past the allocation.

## Impact

OOB heap write of 8 attacker-controlled bytes, plus overwrite of the `widths` pointer, from untrusted JSON given to `dwgwrite` / `dwg_read_json`. No exploit attempted; no claim beyond memory corruption.

## Suggested fix

Apply the 1a12d14e pointer handling to this branch: when `f->type` ends in `*`, use `*(void **)(_obj + f->offset)` and `calloc` the subclass struct when NULL; skip the field if there is no buffer. With it the PoC no longer triggers ASan. (I have not run the test suite / `make check`.)

```diff
-                  void *off = &((char *)_obj)[f->offset];
-                  if (!_set_struct_field (dat, obj, tokens, off, subclass,
-                                          key1, sfields))
+                  void *off;
+                  if (f->type[strlen (f->type) - 1] == '*')
+                    {
+                      off = *(void **)((char *)_obj + f->offset);
+                      if (!off)
+                        {
+                          int subsize = dwg_dynapi_subclass_size (subclass);
+                          if (subsize > 0)
+                            {
+                              off = calloc (1, subsize);
+                              *(void **)((char *)_obj + f->offset) = off;
+                            }
+                        }
+                    }
+                  else
+                    off = &((char *)_obj)[f->offset];
+                  if (!off
+                      || !_set_struct_field (dat, obj, tokens, off, subclass,
+                                             key1, sfields))
                     ++tokens->index;
```

Note: `widths` is semantically a `num_widths`-element array and the exporter emits a JSON array; the object form in the PoC is malformed input. The diff above makes the write safe regardless, but the maintainer may prefer to additionally reject a JSON object here and only accept an array.

