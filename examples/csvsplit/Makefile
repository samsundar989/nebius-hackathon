# CC/CFLAGS come from the environment (Leakproof sets clang + ASan/UBSan).
CC ?= clang
CFLAGS ?= -g -O0

all: csvsplit_fuzz test_csvsplit

libcsvsplit.a: src/csvsplit.c src/csvsplit.h
	$(CC) $(CFLAGS) -c src/csvsplit.c -o csvsplit.o
	ar rcs $@ csvsplit.o

csvsplit_fuzz: fuzz/csvsplit_fuzz.c libcsvsplit.a
	$(CC) $(CFLAGS) -fsanitize=fuzzer fuzz/csvsplit_fuzz.c libcsvsplit.a -o $@

test_csvsplit: tests/test_csvsplit.c libcsvsplit.a
	$(CC) $(CFLAGS) tests/test_csvsplit.c libcsvsplit.a -o $@

test: test_csvsplit
	./test_csvsplit

clean:
	rm -f *.o *.a csvsplit_fuzz test_csvsplit

.PHONY: all test clean
