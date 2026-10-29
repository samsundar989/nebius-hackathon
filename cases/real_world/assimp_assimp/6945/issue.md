# Bug: ASCII STL importer leaks meshes and nodes when parsing fails part-way

https://github.com/assimp/assimp/issues/6945 (opened 2026-10-14T14:59:29Z)

**Describe the bug**

When an ASCII STL file fails to parse part-way, `STLImporter::LoadASCIIFile` (code/AssetLib/STL/STLLoader.cpp) leaks the meshes and nodes it has already allocated. The `aiMesh` / `aiNode` objects are created with `new` at lines 243/247 and kept in local `std::vector<aiMesh *> meshes` / `std::vector<aiNode *> nodes`. They are handed to the scene only after the loop. When the loop throws (for example "STL: Invalid number of vertices"), nobody owns them anymore.

This is not the same situation as #5946, which was closed because the reproducer did not call `aiReleaseImport`. Here the import fails, no scene is returned, and the leak remains after the `Assimp::Importer` is destroyed.

**To Reproduce**

```
solid x
facet normal 0 0 1
outer loop
vertex 0 0 0
vertex 1 0 0
vertex 0 1 0
endloop
endfacet
facet normal 0 0 1
outer loop
vertex 0 0 0
vertex 1 0 0
vertex 0 1 0
endloop
endfacet
facet normal 0 0 1
outer loop
vertex 0 0 0
```

```cpp
#include <assimp/Importer.hpp>
#include <assimp/scene.h>
#include <cstdio>
int main(int argc, char **argv) {
    Assimp::Importer imp;
    const aiScene *s = imp.ReadFile(argv[1], 0);
    printf("%s\n", s ? "scene" : imp.GetErrorString());
}
```

master 3e9c4e1d, ASan/LSan:

```
STL: Invalid number of vertices
Direct leak of 1320 byte(s) in 1 object(s) allocated from:
    #1 Assimp::STLImporter::LoadASCIIFile(aiNode*) code/AssetLib/STL/STLLoader.cpp:243
Direct leak of 1144 byte(s) in 1 object(s) allocated from:
    #1 Assimp::STLImporter::LoadASCIIFile(aiNode*) code/AssetLib/STL/STLLoader.cpp:247
SUMMARY: AddressSanitizer: 2464 byte(s) leaked in 2 allocation(s).
```


**Expected behavior**

No leak when the import fails.

**Possible fix**

Free the collected objects when the loop throws (or hold them in `std::unique_ptr` until they are moved into the scene):

```diff
+    try {
     while (IsAsciiSTL(sz, static_cast<unsigned int>(bufferEnd - sz))) {
 ...
     }
+    } catch (...) {
+        for (aiMesh *m : meshes) delete m;
+        for (aiNode *n : nodes) delete n;
+        throw;
+    }
```

With this change on master, the file above reports no leak. The 8 STL models under test/models and test/models-nonbsd import identically and also show no leaks.

**Platform**

- OS: Linux x86_64 (WSL2), clang 21
- Version: master 3e9c4e1d (also v6.0.5)

---
*Tool-use note (per AIToolPolicy.md): this issue was prepared with the help of an AI assistant (reproducer, measurement and text). The results above were measured on the stated versions.*

