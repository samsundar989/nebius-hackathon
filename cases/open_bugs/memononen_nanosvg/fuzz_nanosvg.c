// Leakproof harness for nanosvg issue #295: parse the input as SVG, print a summary.
// Written for this case (not upstream). nsvgParse modifies its input, so it gets a copy.
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define NANOSVG_IMPLEMENTATION
#include "nanosvg.h"

int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
  char *svg = malloc(size + 1);
  memcpy(svg, data, size);
  svg[size] = '\0';
  NSVGimage *img = nsvgParse(svg, "px", 96.0f);
  int shapes = 0;
  if (img != NULL) {
    for (NSVGshape *s = img->shapes; s != NULL; s = s->next) shapes++;
    printf("%.1fx%.1f shapes=%d\n", img->width, img->height, shapes);
    nsvgDelete(img);
  } else {
    printf("null\n");
  }
  free(svg);
  return 0;
}
