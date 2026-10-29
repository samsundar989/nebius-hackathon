# The toolchain image plus zlib headers, for projects whose configure requires zlib (gpac).
# docker build -t leakproof/cpp-sanitizers:zlib images/cpp-sanitizers-zlib
FROM leakproof/cpp-sanitizers:e0
ARG DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*
