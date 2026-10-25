// Dense BF16 GEMM with FP32 accumulation/output; run under gpu-fleet-run.
#include <cuda_bf16.h>
#include <cuda_runtime.h>
#include <cublas_v2.h>
#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>

constexpr int N = 8192;
constexpr int WARMUP = 200;
constexpr int ITERATIONS = 500;
constexpr int SAMPLES = 5;

void check(cudaError_t status, const char* operation) {
    if (status != cudaSuccess) {
        std::fprintf(stderr, "%s: %s\n", operation, cudaGetErrorString(status));
        std::exit(1);
    }
}
void check(cublasStatus_t status, const char* operation) {
    if (status != CUBLAS_STATUS_SUCCESS) {
        std::fprintf(stderr, "%s: %s\n", operation, cublasGetStatusString(status));
        std::exit(1);
    }
}
#define CHECK(call) check((call), #call)

// Exactly representable inputs allow an independent FP64 reference check.
__host__ __device__ float input_value(unsigned index, unsigned seed) {
    unsigned x = index ^ seed;
    x ^= x >> 16;
    x *= 0x7feb352du;
    x ^= x >> 15;
    x *= 0x846ca68bu;
    x ^= x >> 16;
    return (static_cast<int>(x % 17) - 8) * 0.125f;
}

__global__ void initialize(__nv_bfloat16* a, __nv_bfloat16* b) {
    unsigned i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i < N * N) {
        a[i] = __float2bfloat16(input_value(i, 42));
        b[i] = __float2bfloat16(input_value(i, 1729));
    }
}

struct Matrices {
    __nv_bfloat16 *a = nullptr, *b = nullptr;
    float* c = nullptr;
    cublasHandle_t handle;
};

void multiply(const Matrices& m) {
    const float alpha = 1.0f, beta = 0.0f;
    CHECK(cublasGemmEx(m.handle, CUBLAS_OP_N, CUBLAS_OP_N, N, N, N,
                      &alpha, m.a, CUDA_R_16BF, N, m.b, CUDA_R_16BF, N,
                      &beta, m.c, CUDA_R_32F, N, CUBLAS_COMPUTE_32F,
                      CUBLAS_GEMM_DEFAULT));
}

double verify(const Matrices& m) {
    double max_error = 0;
    for (int sample = 0; sample < 64; ++sample) {
        int row = (sample * 127 + 13) % N;
        int col = (sample * 193 + 29) % N;
        double expected = 0;
        for (int k = 0; k < N; ++k)
            expected += static_cast<double>(input_value(row + k * N, 42)) *
                        input_value(k + col * N, 1729);
        float actual;
        CHECK(cudaMemcpy(&actual, m.c + row + col * N, sizeof(actual), cudaMemcpyDeviceToHost));
        double error = std::abs(static_cast<double>(actual) - expected);
        if (!std::isfinite(actual) || error > 1e-3) {
            std::fprintf(stderr, "Result mismatch (%d,%d): got %.9g expected %.9g\n",
                         row, col, actual, expected);
            std::exit(1);
        }
        max_error = std::max(max_error, error);
    }
    return max_error;
}

long long epoch_ms() {
    return std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::system_clock::now().time_since_epoch()).count();
}

void measure(const Matrices& m) {
    cudaEvent_t start, stop;
    CHECK(cudaEventCreate(&start));
    CHECK(cudaEventCreate(&stop));
    for (int i = 0; i < WARMUP; ++i) multiply(m);
    CHECK(cudaDeviceSynchronize());
    std::array<double, SAMPLES> rates;
    std::printf("\"samples\":[\n");
    for (int sample = 0; sample < SAMPLES; ++sample) {
        const auto started = epoch_ms();
        CHECK(cudaEventRecord(start));
        for (int i = 0; i < ITERATIONS; ++i) multiply(m);
        CHECK(cudaEventRecord(stop));
        CHECK(cudaEventSynchronize(stop));
        const auto finished = epoch_ms();
        float elapsed;
        CHECK(cudaEventElapsedTime(&elapsed, start, stop));
        double gemm_ms = elapsed / ITERATIONS;
        rates[sample] = (2.0 * N * N * N) / (gemm_ms * 1e9);
        std::printf("%s{\"started_epoch_ms\":%lld,\"finished_epoch_ms\":%lld,"
                    "\"gemm_ms\":%.6f,\"tflops\":%.6f}",
                    sample ? ",\n" : "", started, finished, gemm_ms, rates[sample]);
        std::fflush(stdout);
    }
    std::sort(rates.begin(), rates.end());
    std::printf("\n],\"median_tflops\":%.6f,\"max_abs_error\":%.9g,"
                "\"checked_elements\":64,\"complete\":true}\n", rates[SAMPLES / 2], verify(m));
    CHECK(cudaEventDestroy(start));
    CHECK(cudaEventDestroy(stop));
}

int main() {
    const char* node = std::getenv("GPU_FLEET_NODE");
    const char* lease = std::getenv("GPU_FLEET_LEASE_ID");
    if (!node || std::strcmp(node, "proximal") || !lease || !*lease) {
        std::fprintf(stderr, "A proximal GPU fleet lease is required\n");
        return 1;
    }
    CHECK(cudaSetDevice(0));
    cudaDeviceProp gpu;
    CHECK(cudaGetDeviceProperties(&gpu, 0));
    Matrices m;
    CHECK(cublasCreate(&m.handle));
    CHECK(cublasSetMathMode(m.handle, CUBLAS_MATH_DISALLOW_REDUCED_PRECISION_REDUCTION));
    int cublas_version, runtime_version, driver_version;
    CHECK(cublasGetVersion(m.handle, &cublas_version));
    CHECK(cudaRuntimeGetVersion(&runtime_version));
    CHECK(cudaDriverGetVersion(&driver_version));
    const size_t count = static_cast<size_t>(N) * N;
    CHECK(cudaMalloc(&m.a, count * sizeof(*m.a)));
    CHECK(cudaMalloc(&m.b, count * sizeof(*m.b)));
    CHECK(cudaMalloc(&m.c, count * sizeof(*m.c)));
    initialize<<<(count + 255) / 256, 256>>>(m.a, m.b);
    CHECK(cudaGetLastError());
    multiply(m);
    verify(m);
    std::printf("{\"gpu\":\"%s\",\"n\":%d,\"input\":\"BF16\","
                "\"accumulation\":\"FP32\",\"output\":\"FP32\","
                "\"reduced_precision_reduction\":false,\"cublas_version\":%d,"
                "\"cuda_runtime_version\":%d,\"cuda_driver_version\":%d,"
                "\"warmup_iterations\":%d,\"iterations_per_sample\":%d,",
                gpu.name, N, cublas_version, runtime_version, driver_version, WARMUP, ITERATIONS);
    measure(m);
    CHECK(cudaFree(m.a));
    CHECK(cudaFree(m.b));
    CHECK(cudaFree(m.c));
    CHECK(cublasDestroy(m.handle));
}
