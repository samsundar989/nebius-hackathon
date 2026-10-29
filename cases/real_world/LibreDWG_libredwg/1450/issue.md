# in_dxf: heap-buffer-overflow READ in add_LTYPE_dashes (bit_wcs2cpy) on r2007+ DXF linetype with dash text

https://github.com/LibreDWG/libredwg/issues/1450 (opened 2026-10-14T14:02:35Z)

Importing an r2007+ DXF whose LTYPE has a dash text (group 9) reads past the end of the heap buffer that holds the text.

```
  0
SECTION
  2
HEADER
  9
$ACADVER
  1
AC1024
  0
ENDSEC
  0
SECTION
  2
TABLES
  0
TABLE
  2
LTYPE
  5
5
 70
1
  0
LTYPE
  5
3200
100
AcDbSymbolTableRecord
100
AcDbLinetypeTableRecord
  2
CPLX
 70
0
  3
complex
 73
1
 49
0.5
  9
TXT
  0
ENDTAB
  0
ENDSEC
  0
EOF
```

```
dwgwrite -y -I DXF repro.dxf -o out.dwg
```

```
==1176==ERROR: AddressSanitizer: heap-buffer-overflow on address 0x503000000504 at pc 0x562d7cc41846 bp 0x7ffc3d800e70 sp 0x7ffc3d800e60
READ of size 2 at 0x503000000504 thread T0
    #0 in bit_wcs2cpy src/bits.c:2096
    #1 in add_LTYPE_dashes src/in_dxf.c:2491
    #2 in new_object src/in_dxf.c:11778
    #3 in dxf_tables_read src/in_dxf.c:13883
    #4 in dwg_read_dxf src/in_dxf.c:15224

0x503000000504 is located 0 bytes to the right of 20-byte region [0x5030000004f0,0x503000000504)
allocated by thread T0 here:
    #1 in dwg_add_u8_input src/dwg_api.c:24777
    #2 in add_LTYPE_dashes src/in_dxf.c:2476
```

I expected the linetype to import without an out-of-bounds read. Group 9 is the documented LTYPE text string, and the same file with `$ACADVER` set to AC1015 or AC1018 does not overflow under ASan.

The ASan build aborts with the report above (exit 1). That report is from an earlier build; at f860b0fb76d5 it still reproduces, with ASan reporting the heap-buffer-overflow in bit_wcs2len (src/bits.c:2061) instead. The normal build prints `SUCCESS` and exits 0.

This looks like a TU/TV mismatch in in_dxf.c:add_LTYPE_dashes. `is_tu` is taken from `header.version >= R_2007`, but during DXF import `dwg_add_u8_input` returns an 8-bit string (IS_FROM_TU_DWG is false because of DWG_OPTS_INDXF), and `bit_wcs2cpy` then walks that string as UTF-16 until it reaches a zero halfword.

Possibly related: #1263 (closed PR on the LTYPE strings_area in in_dxf).

I can send a patch if that helps.

Found with an LLM-based testing tool; I used Claude to reduce it and look for the cause.

