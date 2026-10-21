/**
 * cuda/src/cpu_baseline.cpp
 * Phase 2 — Sequential CPU preprocessing baseline.
 * Implements Gaussian blur, Sobel edge detection, and Median filter using OpenCV.
 * Provides timing harness: median of N runs, warm-up excluded.
 *
 * Build: cmake -B build && cmake --build build --target cpu_baseline
 * Usage: ./build/cpu_baseline <image_path> [N_runs]
 */
#include <opencv2/opencv.hpp>
#include <chrono>
#include <iostream>
#include <vector>
#include <algorithm>
#include <string>

using Clock = std::chrono::high_resolution_clock;
using Ms    = std::chrono::duration<double, std::milli>;

struct TimingResult {
    double median_ms;
    double min_ms;
    double max_ms;
};

TimingResult bench(std::function<void()> fn, int warmup = 3, int runs = 20) {
    // Warm-up
    for (int i = 0; i < warmup; ++i) fn();
    // Timed runs
    std::vector<double> times;
    times.reserve(runs);
    for (int i = 0; i < runs; ++i) {
        auto t0 = Clock::now();
        fn();
        auto t1 = Clock::now();
        times.push_back(Ms(t1 - t0).count());
    }
    std::sort(times.begin(), times.end());
    double median = (runs % 2 == 0)
        ? (times[runs/2 - 1] + times[runs/2]) / 2.0
        : times[runs/2];
    return {median, times.front(), times.back()};
}

int main(int argc, char* argv[]) {
    if (argc < 2) {
        std::cerr << "Usage: " << argv[0] << " <image_path> [num_runs=20]\n";
        return 1;
    }
    const std::string img_path = argv[1];
    const int N = (argc >= 3) ? std::stoi(argv[2]) : 20;

    cv::Mat img = cv::imread(img_path);
    if (img.empty()) {
        std::cerr << "Error: cannot read image: " << img_path << "\n";
        return 1;
    }

    std::cout << "Image: " << img_path
              << "  Size: " << img.cols << "x" << img.rows
              << "  Runs: " << N << "\n\n";

    // ── 1. Gaussian Blur ────────────────────────────────────────────────────
    {
        cv::Mat out;
        auto res = bench([&]() { cv::GaussianBlur(img, out, {5,5}, 1.0); }, 3, N);
        std::cout << "GaussianBlur  — median: " << res.median_ms << " ms"
                  << "  min: " << res.min_ms << "  max: " << res.max_ms << "\n";
    }

    // ── 2. Sobel Edge Detection ─────────────────────────────────────────────
    {
        cv::Mat gray, sx, sy, mag;
        cv::cvtColor(img, gray, cv::COLOR_BGR2GRAY);
        auto res = bench([&]() {
            cv::Sobel(gray, sx, CV_32F, 1, 0, 3);
            cv::Sobel(gray, sy, CV_32F, 0, 1, 3);
            cv::magnitude(sx, sy, mag);
        }, 3, N);
        std::cout << "Sobel         — median: " << res.median_ms << " ms"
                  << "  min: " << res.min_ms << "  max: " << res.max_ms << "\n";
    }

    // ── 3. Median Filter ────────────────────────────────────────────────────
    {
        cv::Mat out;
        auto res = bench([&]() { cv::medianBlur(img, out, 5); }, 3, N);
        std::cout << "MedianBlur    — median: " << res.median_ms << " ms"
                  << "  min: " << res.min_ms << "  max: " << res.max_ms << "\n";
    }

    return 0;
}
