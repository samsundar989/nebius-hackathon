# Leakproof base image for C/C++ memory-defect reproduction and verification.
# Ubuntu 24.04 ships clang-18 and gcc-13 natively (22.04 would need apt.llvm.org + a toolchain PPA).
FROM ubuntu:24.04

ARG DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
        clang-18 llvm-18 lld-18 libclang-rt-18-dev libc++-18-dev libc++abi-18-dev \
        gcc-13 g++-13 \
        cmake ninja-build make autoconf automake libtool pkg-config \
        valgrind heaptrack afl++ \
        python3 python3-pip git patch diffutils file unzip xz-utils ca-certificates time \
    && rm -rf /var/lib/apt/lists/* \
    && update-alternatives --install /usr/bin/clang clang /usr/bin/clang-18 100 \
    && update-alternatives --install /usr/bin/clang++ clang++ /usr/bin/clang++-18 100 \
    && update-alternatives --install /usr/bin/llvm-symbolizer llvm-symbolizer /usr/bin/llvm-symbolizer-18 100 \
    && update-alternatives --install /usr/bin/gcc gcc /usr/bin/gcc-13 100 \
    && update-alternatives --install /usr/bin/g++ g++ /usr/bin/g++-13 100

# Symbolized, deterministic sanitizer reports by default; callers may override.
ENV ASAN_SYMBOLIZER_PATH=/usr/bin/llvm-symbolizer-18 \
    ASAN_OPTIONS=detect_leaks=1:abort_on_error=0:symbolize=1 \
    UBSAN_OPTIONS=print_stacktrace=1:halt_on_error=0 \
    LSAN_OPTIONS=report_objects=1

RUN mkdir -p /work
WORKDIR /work
