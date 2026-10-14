#!/usr/bin/env bash
# Build the CUDA samples and run NVIDIA compute-sanitizer on them; ncu attempted last.
# Used for the local RTX 5090 (docker --gpus all) and, unchanged, as the Serverless Jobs payload.
set -uo pipefail
SRC=${1:-/cases}
OUT=${2:-/tmp/lp_cuda}
mkdir -p "$OUT"
echo "== nvidia-smi"; nvidia-smi --query-gpu=name,driver_version,compute_cap,memory.total --format=csv
echo "== nvcc"; nvcc --version | tail -2
echo "== compute-sanitizer"; compute-sanitizer --version | head -3
for s in oob_global leak_cudamalloc; do
  nvcc -g -lineinfo -o "$OUT/$s" "$SRC/$s.cu" || echo "BUILD FAILED: $s"
done
echo "== memcheck oob_global"
compute-sanitizer --tool memcheck --print-limit 5 "$OUT/oob_global" > "$OUT/memcheck_oob.log" 2>&1
echo "exit=$?"; cat "$OUT/memcheck_oob.log"
echo "== leak-check leak_cudamalloc"
compute-sanitizer --tool memcheck --leak-check full "$OUT/leak_cudamalloc" > "$OUT/leakcheck.log" 2>&1
echo "exit=$?"; cat "$OUT/leakcheck.log"
echo "== ncu"
if command -v ncu >/dev/null; then
  ncu --metrics gpu__time_duration.sum "$OUT/leak_cudamalloc" > "$OUT/ncu.log" 2>&1; echo "exit=$?"; tail -20 "$OUT/ncu.log"
else
  echo "ncu not found in PATH"; ls /usr/local/cuda/ | grep -i nsight || true
fi
