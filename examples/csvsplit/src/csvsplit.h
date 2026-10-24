#ifndef CSVSPLIT_H
#define CSVSPLIT_H

#include <stddef.h>

/* Split `line` (not NUL-terminated, `len` bytes) at commas. Quoted fields may contain commas
 * and doubled quotes. Returns the number of fields and stores a malloc'd array of malloc'd
 * strings in *fields_out (free with csv_free), or -1 on allocation failure. */
int csv_split(const char *line, size_t len, char ***fields_out);
void csv_free(char **fields, int count);

#endif
