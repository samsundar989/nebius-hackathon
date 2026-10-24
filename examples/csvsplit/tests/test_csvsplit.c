#include <stdio.h>
#include <string.h>

#include "../src/csvsplit.h"

static int failures = 0;

static void expect(const char *line, int want_n, const char *const *want) {
    char **fields;
    int n = csv_split(line, strlen(line), &fields);
    if (n != want_n) {
        printf("FAIL %s: %d fields, want %d\n", line, n, want_n);
        failures++;
    } else {
        for (int i = 0; i < n; i++) {
            if (strcmp(fields[i], want[i]) != 0) {
                printf("FAIL %s: field %d is '%s', want '%s'\n", line, i, fields[i], want[i]);
                failures++;
            }
        }
    }
    if (n >= 0) {
        csv_free(fields, n);
    }
}

int main(void) {
    expect("a,b,c", 3, (const char *const[]){"a", "b", "c"});
    expect("one", 1, (const char *const[]){"one"});
    expect("x,,y", 3, (const char *const[]){"x", "", "y"});
    expect("", 1, (const char *const[]){""});
    expect("1,2,3,4,5,6,7,8,9", 9, (const char *const[]){"1", "2", "3", "4", "5", "6", "7", "8", "9"});
    printf(failures ? "%d failure(s)\n" : "all passed\n", failures);
    return failures != 0;
}
