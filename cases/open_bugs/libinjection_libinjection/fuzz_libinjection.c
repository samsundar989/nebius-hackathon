// Leakproof harness for libinjection issue #90: classify the input, print both verdicts.
// Written for this case (not upstream). libFuzzer's buffer is exactly `size` bytes, so a read of
// s[slen] is caught by AddressSanitizer.
#include <stdint.h>
#include <stdio.h>

#include "libinjection.h"
#include "libinjection_sqli.h"

int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
  const char *s = (const char *) data;
  int xss = (int) libinjection_xss(s, size);
  struct libinjection_sqli_state st;
  libinjection_sqli_init(&st, s, size, FLAG_NONE);
  int sqli = (int) libinjection_is_sqli(&st);
  printf("xss=%d sqli=%d fp=%s\n", xss, sqli, st.fingerprint);
  return 0;
}
