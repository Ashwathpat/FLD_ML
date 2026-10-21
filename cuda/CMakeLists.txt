cmake_minimum_required(VERSION 3.20)
project(fld_preprocessing CUDA CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CUDA_STANDARD 17)

find_package(CUDA REQUIRED)
find_package(OpenCV REQUIRED)

include_directories(${OpenCV_INCLUDE_DIRS})

# ── CPU baseline ──────────────────────────────────────────────────────────────
add_executable(cpu_baseline src/cpu_baseline.cpp)
target_link_libraries(cpu_baseline PRIVATE ${OpenCV_LIBS})

# ── CUDA kernels ─────────────────────────────────────────────────────────────
add_executable(fld_preprocess
    src/kernels_naive.cu
    src/kernels_tiled.cu
    src/batch_streams.cu
    src/main_cuda.cpp
)
target_link_libraries(fld_preprocess PRIVATE ${OpenCV_LIBS})
set_property(TARGET fld_preprocess PROPERTY CUDA_ARCHITECTURES 75 86 89)

# Build options
option(ENABLE_BENCHMARKS "Build benchmark executables" ON)
if(ENABLE_BENCHMARKS)
    add_subdirectory(bench)
endif()
