/* csvsplit: split one CSV line into fields. Demo project for Leakproof's bring-your-own
 * adapter (examples/csvsplit/README.md): small on purpose, with one realistic defect. */
#include "csvsplit.h"

#include <stdlib.h>
#include <string.h>

static char *copy_plain(const char *start, size_t n) {
    char *field = malloc(n + 1);
    if (field == NULL) {
        return NULL;
    }
    memcpy(field, start, n);
    field[n] = '\0';
    return field;
}

/* A quoted field: drop the surrounding quotes, turn "" into ". `raw` points at the opening
 * quote, `n` counts every byte up to and including the closing quote. */
static char *copy_quoted(const char *raw, size_t n) {
    size_t inner = n >= 2 ? n - 2 : 0;
    char *field = malloc(inner); /* room for the content */
    size_t out = 0;
    if (field == NULL) {
        return NULL;
    }
    for (size_t i = 1; i + 1 < n; i++) {
        if (raw[i] == '"' && i + 2 < n && raw[i + 1] == '"') {
            i++;
        }
        field[out++] = raw[i];
    }
    field[out] = '\0';
    return field;
}

int csv_split(const char *line, size_t len, char ***fields_out) {
    size_t cap = 4, count = 0, pos = 0;
    char **fields = malloc(cap * sizeof *fields);
    if (fields == NULL) {
        return -1;
    }
    while (pos <= len) {
        size_t start = pos;
        char *field;
        if (pos < len && line[pos] == '"') {
            pos++;
            while (pos < len && !(line[pos] == '"' && (pos + 1 >= len || line[pos + 1] != '"'))) {
                pos += (line[pos] == '"') ? 2 : 1;
            }
            if (pos < len) {
                pos++; /* closing quote */
            }
            field = copy_quoted(line + start, pos - start);
        } else {
            while (pos < len && line[pos] != ',') {
                pos++;
            }
            field = copy_plain(line + start, pos - start);
        }
        if (field == NULL) {
            csv_free(fields, (int)count);
            return -1;
        }
        if (count == cap) {
            char **grown = realloc(fields, 2 * cap * sizeof *fields);
            if (grown == NULL) {
                free(field);
                csv_free(fields, (int)count);
                return -1;
            }
            fields = grown;
            cap *= 2;
        }
        fields[count++] = field;
        if (pos < len && line[pos] != ',') {
            /* junk after a closing quote: skip to the next delimiter */
            while (pos < len && line[pos] != ',') {
                pos++;
            }
        }
        pos++; /* the delimiter (or one past the end) */
    }
    *fields_out = fields;
    return (int)count;
}

void csv_free(char **fields, int count) {
    for (int i = 0; i < count; i++) {
        free(fields[i]);
    }
    free(fields);
}
