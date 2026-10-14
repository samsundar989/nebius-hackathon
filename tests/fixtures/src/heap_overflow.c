#include <stdlib.h>
int main(void) { int *a = malloc(10 * sizeof(int)); a[10] = 1; free(a); return 0; }
