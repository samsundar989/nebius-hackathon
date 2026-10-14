#include <stdlib.h>
#include <string.h>
static char *make(size_t n) { char *p = malloc(n); memset(p, 'a', n); return p; }
int main(void) { char *p = make(64); p = make(32); free(p); return 0; }
