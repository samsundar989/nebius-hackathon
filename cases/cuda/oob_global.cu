// Injected defect: off-by-one global write (CWE-787). Each of n threads writes out[i + 1],
// so the last thread writes one element past the cudaMalloc'd buffer.
#include <cstdio>
#include <cuda_runtime.h>

__global__ void shift_write(int *out, int n) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i < n) out[i + 1] = i;  // BUG: should be out[i]
}

int main() {
    const int n = 1024;
    int *d = nullptr;
    cudaMalloc(&d, n * sizeof(int));
    shift_write<<<(n + 255) / 256, 256>>>(d, n);
    cudaError_t err = cudaDeviceSynchronize();
    printf("kernel: %s\n", cudaGetErrorString(err));
    cudaFree(d);
    return 0;
}
