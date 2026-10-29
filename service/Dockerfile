# Leakproof demo service. Build context: repo root (render.yaml dockerContext: .).
# Ubuntu 24.04: clang-18 + ASan/LSan runtimes, like images/cpp-sanitizers; setpriv (util-linux)
# drops candidate code to `nobody` (leakproof/runner/local_process.py).
FROM ubuntu:24.04
ARG DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
        clang-18 llvm-18 libclang-rt-18-dev make coreutils util-linux \
        python3 python3-venv ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/bin/clang-18 /usr/bin/clang && ln -sf /usr/bin/clang++-18 /usr/bin/clang++ \
    && ln -sf /usr/bin/llvm-symbolizer-18 /usr/bin/llvm-symbolizer
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    LEAKPROOF_CACHE=/app/cache LEAKPROOF_RUNS=/tmp/runs LEAKPROOF_LOCAL_IMAGES=/tmp \
    ASAN_SYMBOLIZER_PATH=/usr/bin/llvm-symbolizer
WORKDIR /app
RUN python3 -m venv /venv && /venv/bin/pip install --no-cache-dir \
        "fastapi==0.115.6" "uvicorn==0.34.0" "openai>=1.60" "jsonschema>=4.23" "httpx>=0.27"
COPY leakproof /app/leakproof
COPY service/app.py /app/service_app.py
COPY service/recorded /app/recorded
COPY service/reverify /app/reverify
COPY service/juliet/cases /app/cases/juliet
COPY service/juliet/C /app/cache/juliet/C
COPY service/juliet/cases.txt /app/juliet/cases.txt
# The API runs as root only so it can drop candidate code to `nobody`; it holds no files of value.
ENV PATH=/venv/bin:$PATH PYTHONPATH=/app
CMD ["sh", "-c", "uvicorn service_app:app --host 0.0.0.0 --port ${PORT:-10000}"]
