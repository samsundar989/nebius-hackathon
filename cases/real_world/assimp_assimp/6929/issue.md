# Heap-buffer-overflow in MD2Importer::ValidateHeader via 32-bit wraparound in the frame-table check

https://github.com/assimp/assimp/issues/6929 (opened 2026-10-13T17:23:30Z)

## The bug

`MD2Importer::ValidateHeader()` bounds-checks the animation-frame table with the 32-bit expression
`offsetFrames + numFrames * frameSize`, where `frameSize = 44 + (numVertices - 1) * 4` is computed
in `unsigned int`. Both factors are file-controlled 32-bit values, so the multiplication **wraps
modulo 2³²**: crafted counts make the validator believe the frame data fits while the real region
lies billions of bytes beyond the file. The importer then derives the vertex pointer from the
accepted frame region and dereferences it with a triangle index below `numVertices` (so the index
clamp does not fire), reading 8 bytes past the whole-file heap buffer.

- **Affected:** assimp 6.0.5 (latest release) and current master — the affected code is unchanged
  (no fix commit as of 2026-10-13).
- **Default configuration:** no import options or keyframe selection are required — a plain
  `ReadFile` of a crafted `.md2` triggers it.

## ASan report (6.0.5, default configuration)

```text
==ERROR: AddressSanitizer: heap-buffer-overflow on address 0x79a3123fe868
READ of size 1 at 0x79a3123fe868 thread T0
    #0 Assimp::MD2Importer::InternReadFile   MD2Loader.cpp:406
    #1 Assimp::BaseImporter::ReadFile        BaseImporter.cpp:131
    #2 Assimp::Importer::ReadFile            Importer.cpp:709
0x79a3123fe868 is located 8 bytes after 262240-byte region
allocated by thread T0 here:
    #... Assimp::MD2Importer::InternReadFile  MD2Loader.cpp:212
SUMMARY: AddressSanitizer: heap-buffer-overflow MD2Loader.cpp:406 in MD2Importer::InternReadFile
```

Reproduced 3/3 runs (exit 134) using the stock `assimp` CLI on an ASan build. The same payload
against master crashes identically at `MD2Loader.cpp:409`.

## Root cause and vulnerable code

`code/AssetLib/MD2/MD2Loader.cpp` (6.0.5):

```cpp
:171  unsigned int frameSize = sizeof (MD2::Frame) + (m_pcHeader->numVertices - 1) * sizeof(MD2::Vertex);
...
:176  m_pcHeader->offsetFrames + m_pcHeader->numFrames * frameSize >= fileSize ||   // 32-bit, wraps
...
:212  std::vector<uint8_t> mBuffer2(fileSize);                            // whole-file heap buffer
:257-258  pcFrame = m_pcHeader + m_pcHeader->offsetFrames + (m_pcHeader->frameSize * configFrameID);
:398  if (iIndex >= m_pcHeader->numVertices) iIndex = m_pcHeader->numVertices - 1;   // does not fire
:406  vec.x = (float)pcVerts[iIndex].vertex[0] * pcFrame->scale[0];      // OOB read
```

Concrete numbers (PoC): `numVertices = 131,062` → `frameSize = 44 + 131,061 * 4 = 524,288 (2¹⁹)`;
`numFrames = 8,192 (2¹³)` → `numFrames * frameSize = 2³² ≡ 0 (mod 2³²)`. The validator evaluates
`offsetFrames + 0 = 68 < 262,240` and accepts a frame region that would really occupy ~4 GiB. At
runtime (default keyframe 0): `pcVerts = base + 108`; the triangle index `65,535` is below
`numVertices`, so the read `pcVerts[65,535].vertex[0]` lands at `262,248` — **8 bytes past the
262,240-byte buffer**. Existing count caps (`AI_MAX_ALLOC`) allow both values.

## Reproduction

Payloads are in the attached PoC bundle (`poc/` = `poc_wrap.md2`, `ctrl_nowrap.md2`,
`baseline_ok.md2`, `gen_md2.py`; `evidence/` = run logs). Short form:

```bash
# 1. build 6.0.5 with ASan (MD2 importer only)
cmake -S assimp-6.0.5 -B build-asan -G Ninja -DCMAKE_BUILD_TYPE=RelWithDebInfo \
  -DASSIMP_BUILD_TESTS=OFF -DASSIMP_BUILD_SAMPLES=OFF -DASSIMP_BUILD_ALL_IMPORTERS_BY_DEFAULT=OFF \
  -DASSIMP_BUILD_MD2_IMPORTER=ON -DBUILD_SHARED_LIBS=OFF \
  -DCMAKE_C_FLAGS="-fsanitize=address -g -fno-omit-frame-pointer" \
  -DCMAKE_CXX_FLAGS="-fsanitize=address -g -fno-omit-frame-pointer" -DCMAKE_EXE_LINKER_FLAGS="-fsanitize=address"
cmake --build build-asan -j"$(nproc)"

# 2. run (default configuration — no import options)
ASAN_OPTIONS=detect_leaks=0:abort_on_error=1 build-asan/bin/assimp info poc/poc_wrap.md2      # crash
ASAN_OPTIONS=detect_leaks=0:abort_on_error=1 build-asan/bin/assimp info poc/ctrl_nowrap.md2   # rejected cleanly
ASAN_OPTIONS=detect_leaks=0:abort_on_error=1 build-asan/bin/assimp info poc/baseline_ok.md2   # OK
```

`ctrl_nowrap.md2` (`numFrames = 8,191`, no wrap) is rejected with
*"Invalid MD2 header: Some offsets are outside the file"* — confirming the crash is specific to the
wraparound.

## Impact

A malformed MD2 file deterministically crashes the importing process — the heap-buffer-overflow
aborts in instrumented builds; on uninstrumented builds the OOB read crashes or over-reads
depending on heap layout. **No keyframe selection or other application behaviour is needed** — any
application that imports untrusted `.md2` models through the default API is affected.
Suggested CVSS 3.1: `AV:L/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:H` (6.1, Medium).

## Suggested fix

1. Perform the frame-table arithmetic in 64-bit (or checked/saturating) arithmetic:
   `(uint64_t)offsetFrames + (uint64_t)numFrames * frameSize <= fileSize`.
2. Validate the region that will actually be dereferenced, not just the table:
   `offsetFrames + configFrameID * frameSize + sizeof(Frame) + numVertices * sizeof(Vertex) <= fileSize`.
3. Keep the existing count caps and additionally reject headers whose computed `frameSize` cannot be
   validated without wrapping.
