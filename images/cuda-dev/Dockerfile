# Leakproof CUDA image: nvcc + compute-sanitizer (ships with the devel toolkit).
FROM nvidia/cuda:12.6.3-devel-ubuntu22.04

ARG DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
        cmake ninja-build python3 git patch ca-certificates \
    && rm -rf /var/lib/apt/lists/*

ENV PATH=/usr/local/cuda/bin:${PATH}
RUN mkdir -p /work
WORKDIR /work
