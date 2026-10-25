// Leakproof harness for yajl issue #260: parse the input with callbacks (strings are decoded),
// print event counts. Written for this case (not upstream; the reporter's harness is not public).
#include <stdint.h>
#include <stdio.h>

#include <yajl/yajl_parse.h>

struct counts {
  int values, strings, keys, maps, arrays;
  size_t string_bytes;
};

static int on_null(void *c) { ((struct counts *) c)->values++; return 1; }
static int on_bool(void *c, int b) { (void) b; ((struct counts *) c)->values++; return 1; }
static int on_number(void *c, const char *s, size_t l) { (void) s; (void) l; ((struct counts *) c)->values++; return 1; }
static int on_string(void *c, const unsigned char *s, size_t l) {
  (void) s;
  ((struct counts *) c)->strings++;
  ((struct counts *) c)->string_bytes += l;
  return 1;
}
static int on_key(void *c, const unsigned char *s, size_t l) { (void) s; (void) l; ((struct counts *) c)->keys++; return 1; }
static int on_start_map(void *c) { ((struct counts *) c)->maps++; return 1; }
static int on_end(void *c) { (void) c; return 1; }
static int on_start_array(void *c) { ((struct counts *) c)->arrays++; return 1; }

static const yajl_callbacks callbacks = {
    on_null, on_bool, NULL, NULL, on_number, on_string,
    on_start_map, on_key, on_end, on_start_array, on_end};

int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
  struct counts c = {0};
  yajl_handle h = yajl_alloc(&callbacks, NULL, &c);
  yajl_config(h, yajl_allow_comments, 1);
  yajl_status st = yajl_parse(h, data, size);
  if (st == yajl_status_ok) st = yajl_complete_parse(h);
  printf("status=%d values=%d strings=%d bytes=%zu keys=%d maps=%d arrays=%d\n", (int) st,
         c.values, c.strings, c.string_bytes, c.keys, c.maps, c.arrays);
  yajl_free(h);
  return 0;
}
