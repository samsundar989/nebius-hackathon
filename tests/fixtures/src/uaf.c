#include <stdlib.h>
#include <stdio.h>
static void release(char *p) { free(p); }
int main(void) { char *p = malloc(16); release(p); printf("%c\n", p[1]); return 0; }
