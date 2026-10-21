/**
 * cuda/src/batch_streams.cu
 * Phase 4 — Multi-stream batch pipeline.
 * Processes a list of images using pinned host memory and cudaMemcpyAsync
 * across N CUDA streams to overlap H→D transfer, kernel, and D→H copy.
 *
 * Streams: 1, 2, 4, 8 (benchmarked in bench/bench_streams.sh)
 */
#include <cuda_runtime.h>
#include <device_launch_parameters.h>
#include <vector>
#include <string>
#include <cstdio>

// Declared in kernels_naive.cu / kernels_tiled.cu
extern void upload_gauss_kernel();
extern __global__ void gaussian_tiled(
    const unsigned char*, unsigned char*, int, int, int);

struct ImageBatch {
    unsigned char* h_src;   // Pinned host memory for source images
    unsigned char* h_dst;   // Pinned host memory for output images
    unsigned char* d_src;   // Device source buffer
    unsigned char* d_dst;   // Device output buffer
    int width, height, channels;
    size_t image_bytes;
};

void run_batch_pipeline(
    std::vector<ImageBatch>& images,
    int num_streams = 4)
{
    upload_gauss_kernel();

    std::vector<cudaStream_t> streams(num_streams);
    for (auto& s : streams) cudaStreamCreate(&s);

    for (size_t i = 0; i < images.size(); ++i) {
        auto& img = images[i];
        int sid = i % num_streams;
        cudaStream_t stream = streams[sid];

        // Async copy H→D
        cudaMemcpyAsync(img.d_src, img.h_src, img.image_bytes, cudaMemcpyHostToDevice, stream);

        // Launch tiled kernel
        dim3 block(16, 16);
        dim3 grid(
            (img.width  + block.x - 1) / block.x,
            (img.height + block.y - 1) / block.y
        );
        gaussian_tiled<<<grid, block, 0, stream>>>(
            img.d_src, img.d_dst, img.width, img.height, img.channels);

        // Async copy D→H
        cudaMemcpyAsync(img.h_dst, img.d_dst, img.image_bytes, cudaMemcpyDeviceToHost, stream);
    }

    for (auto& s : streams) {
        cudaStreamSynchronize(s);
        cudaStreamDestroy(s);
    }

    printf("[batch_streams] Processed %zu images with %d streams\n",
           images.size(), num_streams);
}
