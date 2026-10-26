/* vks/special-fun issue #17: facf with an out-of-range argument ("facf overflow error" in the
   issue's report) returns MAXNUMF, which facf.c declares as double and constf.c defines as float. */
#include <stdio.h>
float facf(int i);

int main(void) {
  printf("%g\n", facf(34));
  return 0;
}
