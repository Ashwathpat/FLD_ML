/**
 * cuda/src/kernels_tiled.cu
 * Phase 3 — Optimised CUDA kernels using shared-memory tiling with halo regions
 * and constant-memory Gaussian coefficients.
 * Block sizes: 16×16 (compare 8×8 and 32×32 in benchmarks).
 */
#include <cuda_runtime.h>
#include <device_launch_parameters.h>
#include <cmath>

#define TILE_W 16
#define TILE_H 16
#define HALO   2   // For 5×5 kernel

extern __constant__ float d_gauss5x5[25];

// ── Tiled Gaussian Blur ───────────────────────────────────────────────────────
__global__ void gaussian_tiled(
    const unsigned char* __restrict__ src,
    unsigned char* __restrict__ dst,
    int width, int height, int channels)
{
    // Shared memory tile including halo border
    __shared__ float smem[TILE_H + 2*HALO][TILE_W + 2*HALO];

    int tx = threadIdx.x, ty = threadIdx.y;
    int col = blockIdx.x * TILE_W + tx;
    int row = blockIdx.y * TILE_H + ty;

    for (int c = 0; c < channels; ++c) {
        // Load tile + halo into shared memory
        int smem_col = tx + HALO;
        int smem_row = ty + HALO;
        int clamped_col = min(max(col, 0), width  - 1);
        int clamped_row = min(max(row, 0), height - 1);

        smem[smem_row][smem_col] = src[(clamped_row * width + clamped_col) * channels + c];

        // Load left halo
        if (tx < HALO) {
            int lc = min(max(col - HALO, 0), width - 1);
            smem[smem_row][tx] = src[(clamped_row * width + lc) * channels + c];
        }
        // Load right halo
        if (tx >= TILE_W - HALO) {
            int rc = min(col + HALO, width - 1);
            smem[smem_row][smem_col + HALO] = src[(clamped_row * width + rc) * channels + c];
        }
        // Load top halo
        if (ty < HALO) {
            int tr = min(max(row - HALO, 0), height - 1);
            smem[ty][smem_col] = src[(tr * width + clamped_col) * channels + c];
        }
        // Load bottom halo
        if (ty >= TILE_H - HALO) {
            int br = min(row + HALO, height - 1);
            smem[smem_row + HALO][smem_col] = src[(br * width + clamped_col) * channels + c];
        }
        __syncthreads();

        if (col >= width || row >= height) { __syncthreads(); continue; }

        float acc = 0.f;
        #pragma unroll
        for (int ky = 0; ky < 5; ++ky)
            #pragma unroll
            for (int kx = 0; kx < 5; ++kx)
                acc += d_gauss5x5[ky*5 + kx] * smem[ty + ky][tx + kx];

        dst[(row * width + col) * channels + c] = (unsigned char)fminf(fmaxf(acc, 0.f), 255.f);
        __syncthreads();
    }
}
