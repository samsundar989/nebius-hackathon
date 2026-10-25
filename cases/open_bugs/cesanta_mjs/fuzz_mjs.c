// Leakproof harness for cesanta/mjs issue #324: run the input as a script, print the outcome.
// Written for this case (not upstream). The input is copied to a NUL-terminated heap buffer, as
// mjs_exec_file does, so a read past the terminator is caught by AddressSanitizer.
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "mjs.h"

int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
  char *src = malloc(size + 1);
  memcpy(src, data, size);
  src[size] = '\0';
  struct mjs *mjs = mjs_create();
  mjs_val_t res = 0;
  mjs_err_t err = mjs_exec(mjs, src, &res);
  if (err == MJS_OK && mjs_is_number(res)) {
    printf("ok number %g\n", mjs_get_double(mjs, res));
  } else {
    printf("%s %d\n", err == MJS_OK ? "ok" : "err", (int) err);
  }
  mjs_destroy(mjs);
  free(src);
  return 0;
}
