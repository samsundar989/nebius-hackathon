// Leakproof harness for chmod222/cNBT issue #28: parse the input as uncompressed NBT, print the
// tree size, free it. Written for this case (not upstream).
#include <stdint.h>
#include <stdio.h>

#include "nbt.h"

int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
  nbt_node *tree = nbt_parse(data, size);
  if (tree != NULL) {
    printf("ok size=%zu\n", nbt_size(tree));
    nbt_free(tree);
  } else {
    printf("error\n");
  }
  return 0;
}
