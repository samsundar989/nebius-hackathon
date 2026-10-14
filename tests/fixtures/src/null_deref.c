#include <stdio.h>
struct s { int x; };
static int get(struct s *p) { return p->x; }
int main(int argc, char **argv) { (void)argv; struct s *p = argc > 5 ? (struct s *)argv : NULL; printf("%d\n", get(p)); return 0; }
