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
    cudaMemset(d, 0, n * sizeof(int));
    shift_write<<<(n + 255) / 256, 256>>>(d, n);
    cudaError_t err = cudaDeviceSynchronize();
    int h[n];
    cudaMemcpy(h, d, n * sizeof(int), cudaMemcpyDeviceToHost);
    long long sum = 0;
    for (int i = 0; i < n; i++) sum += (long long)h[i] * (i + 1);
    printf("kernel: %s\nchecksum: %lld\n", cudaGetErrorString(err), sum);
    cudaFree(d);
    return 0;
}
