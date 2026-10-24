// Injected defect: device allocation never freed (CWE-401), detected by --leak-check full.
#include <cstdio>
#include <cuda_runtime.h>

__global__ void fill(float *v, int n, float x) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i < n) v[i] = x;
}

static float *make_buffer(int n, float x) {
    float *d = nullptr;
    cudaMalloc(&d, n * sizeof(float));
    fill<<<(n + 255) / 256, 256>>>(d, n, x);
    return d;
}

static double total(const float *d, int n) {
    float *h = new float[n];
    cudaMemcpy(h, d, n * sizeof(float), cudaMemcpyDeviceToHost);
    double s = 0;
    for (int i = 0; i < n; i++) s += h[i];
    delete[] h;
    return s;
}

int main() {
    float *a = make_buffer(4096, 1.0f);
    float *b = make_buffer(1024, 2.0f);
    cudaDeviceSynchronize();
    printf("total: %.1f\n", total(a, 4096) + total(b, 1024));
    cudaFree(a);  // BUG: b is never freed
    printf("done\n");
    return 0;
}
