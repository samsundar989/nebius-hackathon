#include <string.h>
int main(int argc, char **argv) { (void)argv; char buf[8]; memset(buf, 0, 8 + argc); return buf[0]; }
