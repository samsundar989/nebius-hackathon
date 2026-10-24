#include <stddef.h>
#include <stdint.h>

#include "../src/csvsplit.h"

int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
    char **fields;
    int n = csv_split((const char *)data, size, &fields);
    if (n >= 0) {
        csv_free(fields, n);
    }
    return 0;
}
