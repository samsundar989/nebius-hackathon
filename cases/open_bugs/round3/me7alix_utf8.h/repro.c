/* me7alix/utf8.h issue #1: the issue's inline sample (the last string reads past its end). */
#include <stdio.h>
#include "utf8.h"

int main(void) {
  char *strings[] = {"\xC0\xAF", "\xE0\x80\xAF", "\xF0\x80\x80\xAF", "\xED\xA0\x80", "\xE2:6", "\xF0", 0};
  for (char **string = strings; *string; string++) {
    size_t bytes_read;
    UTF8_Rune code_point = utf8_decode(*string, &bytes_read);
    printf("code_point = %x, bytes_read = %zu\n", code_point, bytes_read);
  }
  return 0;
}
