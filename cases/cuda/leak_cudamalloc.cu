// Injected defect: device allocation never freed (CWE-401), detected by --leak-check full.
#include <cstdio>
#include <cuda_runtime.h>

__global__ void fill(float *v, int n, float x) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i < n) v[i] = x;
}

static float *make_buffer(int n) {
    float *d = nullptr;
    cudaMalloc(&d, n * sizeof(float));
    fill<<<(n + 255) / 256, 256>>>(d, n, 1.0f);
    return d;
}

int main() {
    float *a = make_buffer(4096);
    float *b = make_buffer(1024);
    cudaDeviceSynchronize();
    cudaFree(a);  // BUG: b is never freed
    printf("done\n");
    (void)b;
    return 0;
}
