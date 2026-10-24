// Injected defect: shared-memory data race (CWE-362) in a block reduction. Threads read their
// neighbours' partial sums in the next step without a barrier, so racecheck reports a hazard.
#include <cstdio>
#include <cuda_runtime.h>

#define THREADS 256

__global__ void block_sum(const int *in, int *out, int n) {
    __shared__ int part[THREADS];
    int t = threadIdx.x;
    int i = blockIdx.x * blockDim.x + t;
    part[t] = i < n ? in[i] : 0;
    __syncthreads();
    for (int stride = THREADS / 2; stride > 0; stride /= 2) {
        if (t < stride) part[t] += part[t + stride];
        // BUG: missing __syncthreads() before the next step reads part[t + stride]
    }
    if (t == 0) out[blockIdx.x] = part[0];
}

int main() {
    const int n = 1 << 14, blocks = n / THREADS;
    int *h = new int[n];
    for (int i = 0; i < n; i++) h[i] = i % 7;
    int *d_in = nullptr, *d_out = nullptr;
    cudaMalloc(&d_in, n * sizeof(int));
    cudaMalloc(&d_out, blocks * sizeof(int));
    cudaMemcpy(d_in, h, n * sizeof(int), cudaMemcpyHostToDevice);
    block_sum<<<blocks, THREADS>>>(d_in, d_out, n);
    int *sums = new int[blocks];
    cudaMemcpy(sums, d_out, blocks * sizeof(int), cudaMemcpyDeviceToHost);
    long long total = 0;
    for (int b = 0; b < blocks; b++) total += sums[b];
    printf("total: %lld\n", total);
    cudaFree(d_in);
    cudaFree(d_out);
    delete[] h;
    delete[] sums;
    return 0;
}
