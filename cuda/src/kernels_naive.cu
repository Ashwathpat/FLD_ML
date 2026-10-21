/**
 * cuda/src/kernels_naive.cu
 * Phase 3 — Naïve CUDA kernels: one thread per output pixel.
 * Implements Gaussian blur, Sobel, and Median filter.
 * Verified against CPU reference (max-abs-diff, PSNR).
 */
#include <cuda_runtime.h>
#include <device_launch_parameters.h>
#include <cmath>
#include <cstdio>

// ── Gaussian kernel coefficients (5×5, sigma=1.0, stored in constant mem) ────
__constant__ float d_gauss5x5[25];

static const float h_gauss5x5[25] = {
    1/256.f,  4/256.f,  6/256.f,  4/256.f,  1/256.f,
    4/256.f, 16/256.f, 24/256.f, 16/256.f,  4/256.f,
    6/256.f, 24/256.f, 36/256.f, 24/256.f,  6/256.f,
    4/256.f, 16/256.f, 24/256.f, 16/256.f,  4/256.f,
    1/256.f,  4/256.f,  6/256.f,  4/256.f,  1/256.f,
};

void upload_gauss_kernel() {
    cudaMemcpyToSymbol(d_gauss5x5, h_gauss5x5, 25 * sizeof(float));
}

// ── Naïve Gaussian Blur ───────────────────────────────────────────────────────
__global__ void gaussian_naive(
    const unsigned char* __restrict__ src,
    unsigned char* __restrict__ dst,
    int width, int height, int channels)
{
    int col = blockIdx.x * blockDim.x + threadIdx.x;
    int row = blockIdx.y * blockDim.y + threadIdx.y;
    if (col >= width || row >= height) return;

    for (int c = 0; c < channels; ++c) {
        float acc = 0.f;
        for (int ky = -2; ky <= 2; ++ky) {
            for (int kx = -2; kx <= 2; ++kx) {
                int sr = min(max(row + ky, 0), height - 1);
                int sc = min(max(col + kx, 0), width  - 1);
                float coeff = d_gauss5x5[(ky+2)*5 + (kx+2)];
                acc += coeff * src[(sr * width + sc) * channels + c];
            }
        }
        dst[(row * width + col) * channels + c] = (unsigned char)fminf(fmaxf(acc, 0.f), 255.f);
    }
}

// ── Naïve Sobel (grayscale) ───────────────────────────────────────────────────
__global__ void sobel_naive(
    const unsigned char* __restrict__ gray,
    unsigned char* __restrict__ dst,
    int width, int height)
{
    int col = blockIdx.x * blockDim.x + threadIdx.x;
    int row = blockIdx.y * blockDim.y + threadIdx.y;
    if (col >= width || row >= height) return;

    float gx = 0.f, gy = 0.f;
    const int Kx[9] = {-1,0,1, -2,0,2, -1,0,1};
    const int Ky[9] = {-1,-2,-1, 0,0,0, 1,2,1};
    for (int ky = -1; ky <= 1; ++ky) {
        for (int kx = -1; kx <= 1; ++kx) {
            int sr = min(max(row + ky, 0), height - 1);
            int sc = min(max(col + kx, 0), width  - 1);
            float v = gray[sr * width + sc];
            gx += Kx[(ky+1)*3 + (kx+1)] * v;
            gy += Ky[(ky+1)*3 + (kx+1)] * v;
        }
    }
    dst[row * width + col] = (unsigned char)fminf(sqrtf(gx*gx + gy*gy), 255.f);
}

// ── Naïve Median (3×3, grayscale only for speed) ─────────────────────────────
__device__ void sort9(float* a) {
    // Simple bubble sort of 9 elements on device
    for (int i = 0; i < 9; ++i)
        for (int j = 0; j < 8 - i; ++j)
            if (a[j] > a[j+1]) { float t = a[j]; a[j] = a[j+1]; a[j+1] = t; }
}

__global__ void median_naive(
    const unsigned char* __restrict__ src,
    unsigned char* __restrict__ dst,
    int width, int height, int channels)
{
    int col = blockIdx.x * blockDim.x + threadIdx.x;
    int row = blockIdx.y * blockDim.y + threadIdx.y;
    if (col >= width || row >= height) return;

    for (int c = 0; c < channels; ++c) {
        float window[9];
        int k = 0;
        for (int ky = -1; ky <= 1; ++ky) {
            for (int kx = -1; kx <= 1; ++kx) {
                int sr = min(max(row + ky, 0), height - 1);
                int sc = min(max(col + kx, 0), width  - 1);
                window[k++] = src[(sr * width + sc) * channels + c];
            }
        }
        sort9(window);
        dst[(row * width + col) * channels + c] = (unsigned char)window[4];
    }
}
