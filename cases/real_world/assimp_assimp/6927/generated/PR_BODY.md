AddressSanitizer reports a heap-buffer-underflow in
glTF2::Buffer::Read() (code/AssetLib/glTF2/glTF2Asset.inl:606).

The change, in code/AssetLib/glTF2/glTF2Asset.inl:

    +            }
    +
    +            // Bounds check: ensure dataURI.data points within the original URI string
    +            if (dataURI.data == nullptr || dataURI.data < uri || dataURI.data + dataURI.dataLength > uri + it->GetStringLength()) {
    +                throw DeadlyImportError("GLTF: buffer \"", id, "\" has invalid data URI");

Not fixed here: ParseDataURI still packs the data offset into a signed char (glTFCommon.cpp:88); the base64 branch of Buffer::Read, glTF2 image data URIs (glTF2Asset.inl:1192) and the glTF 1 importer (glTFAsset.inl:195, 513) still receive the wrapped pointer. This change only bounds-checks the raw-data copy that the PoC reaches.

Tested: the reproducer from the issue runs clean under AddressSanitizer/UBSan; the project's own tests pass; variants of the crash input found no new crash.

This patch was developed with Leakproof, an AI repair agent; its candidate passed sanitizer-based checks. I reviewed the change and ran the project's tests myself.

Part of #6927.
