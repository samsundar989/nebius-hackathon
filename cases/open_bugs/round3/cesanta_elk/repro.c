/* cesanta/elk issue #82: the issue's "unclosed string" reproducer (a bounded slice, no NUL). */
#include <stdlib.h>
#include <string.h>
#include "elk.h"

int main(void) {
  char mem[8192];
  struct js *js = js_create(mem, sizeof(mem));
  char *s = malloc(6);
  memcpy(s, "\"abcde", 6); /* quote + 5 letters; no closer, no NUL */
  js_eval(js, s, 6);
  free(s);
  return 0;
}
