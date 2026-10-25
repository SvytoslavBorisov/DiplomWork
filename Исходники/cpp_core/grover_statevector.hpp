#pragma once

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <limits>
#include <random>
#include <stdexcept>
#include <string>
#include <vector>

// Выполняет фазовый оракул, диффузию и измерение полного вещественного вектора амплитуд.
namespace grover_statevector {

struct Limits {
    uint64_t max_states = 1048576;
    uint64_t max_work = 200000000;
    uint64_t max_memory_bytes = 536870912;
    double timeout_seconds = 30.0;
};

inline Limits current_limits() {
    Limits limits;
    auto lower = [](const char* name, uint64_t maximum) {
        const char* raw = std::getenv(name);
        if (!raw) return maximum;
        const std::string text(raw);
        if (text.empty() || text.front() == '-') throw std::runtime_error("Лимит ресурсов должен быть положительным.");
        size_t consumed = 0;
        const uint64_t value = std::stoull(text, &consumed);
        if (!value || consumed != text.size()) throw std::runtime_error("Некорректный лимит ресурсов.");
        return std::min(value, maximum);
    };
    limits.max_states = lower("GROVER_MAX_STATES", limits.max_states);
    limits.max_work = lower("GROVER_MAX_WORK", limits.max_work);
    limits.max_memory_bytes = lower("GROVER_MAX_MEMORY_BYTES", limits.max_memory_bytes);
    if (const char* raw = std::getenv("GROVER_TIMEOUT_SECONDS")) {
        const double seconds = std::stod(raw);
        if (!std::isfinite(seconds) || seconds <= 0) throw std::runtime_error("Время симуляции должно быть положительным.");
        limits.timeout_seconds = std::min(seconds, limits.timeout_seconds);
    }
    return limits;
}

inline void check_resources(uint64_t states, uint64_t iterations, uint64_t other_bytes = 0) {
    const auto limits = current_limits();
    if (!states) throw std::runtime_error("Пространство вектора амплитуд должно быть непустым.");
    if (states > limits.max_states || states > std::numeric_limits<size_t>::max())
        throw std::runtime_error("Размер вектора амплитуд S=" + std::to_string(states) + " превышает лимит " + std::to_string(limits.max_states) + ".");
    if (iterations > limits.max_work / states)
        throw std::runtime_error("Объём симуляции S × iterations превышает лимит " + std::to_string(limits.max_work) + ".");
    if (other_bytes > limits.max_memory_bytes || states > (limits.max_memory_bytes - other_bytes) / 9)
        throw std::runtime_error("Оценка памяти симулятора превышает лимит " + std::to_string(limits.max_memory_bytes) + " байт.");
}

class Deadline {
public:
    Deadline(): start_(std::chrono::steady_clock::now()), seconds_(current_limits().timeout_seconds) {}
    void check() const {
        if (elapsed() > seconds_) throw std::runtime_error("Превышен лимит времени моделирования вектора амплитуд.");
    }
    double elapsed() const { return std::chrono::duration<double>(std::chrono::steady_clock::now() - start_).count(); }
private:
    std::chrono::steady_clock::time_point start_;
    double seconds_;
};

// Суммирует значения с компенсацией ошибок округления без изменения амплитуд.
struct CompensatedSum {
    double value = 0.0, correction = 0.0;
    void add(double item) {
        const double adjusted = item - correction;
        const double next = value + adjusted;
        correction = (next - value) - adjusted;
        value = next;
    }
};

inline void apply_phase_oracle(std::vector<double>& amplitudes, const std::vector<uint8_t>& marked) {
    if (amplitudes.size() != marked.size()) throw std::runtime_error("Размеры оракула и вектора амплитуд различаются.");
    for (size_t i = 0; i < amplitudes.size(); ++i) if (marked[i]) amplitudes[i] = -amplitudes[i];
}

inline void apply_diffusion(std::vector<double>& amplitudes) {
    if (amplitudes.empty()) throw std::runtime_error("Диффузия требует непустого вектора амплитуд.");
    CompensatedSum sum;
    for (double value : amplitudes) sum.add(value);
    const double twice_mean = 2.0 * sum.value / static_cast<double>(amplitudes.size());
    for (double& value : amplitudes) value = twice_mean - value;
}

struct Result {
    size_t measured_index = 0;
    bool is_marked = false;
    uint64_t marked_count = 0;
    uint64_t iterations = 0;
    uint64_t oracle_queries = 0;
    double success_probability = 0.0;
    double norm_error = 0.0;
    uint64_t statevector_elements_processed = 0;
    double statevector_seconds = 0.0;
};

inline Result simulate_grover_statevector(const std::vector<uint8_t>& marked, uint64_t iterations,
                                         std::mt19937_64& rng, std::vector<double>* final_amplitudes = nullptr) {
    const uint64_t states = static_cast<uint64_t>(marked.size());
    check_resources(states, iterations, final_amplitudes ? states * sizeof(double) : 0);
    Deadline deadline;
    Result result;
    result.iterations = iterations;
    result.oracle_queries = iterations + 1;
    for (uint8_t flag : marked) {
        if (flag > 1) throw std::runtime_error("Признак помеченного элемента должен быть 0 или 1.");
        result.marked_count += flag;
    }
    std::vector<double> amplitudes(static_cast<size_t>(states), 1.0 / std::sqrt(static_cast<double>(states)));
    for (uint64_t iteration = 0; iteration < iterations; ++iteration) {
        deadline.check();
        apply_phase_oracle(amplitudes, marked);
        apply_diffusion(amplitudes);
    }
    CompensatedSum probability_sum, marked_probability;
    for (size_t i = 0; i < amplitudes.size(); ++i) {
        const double probability = amplitudes[i] * amplitudes[i];
        probability_sum.add(probability);
        if (marked[i]) marked_probability.add(probability);
    }
    result.success_probability = marked_probability.value;
    result.norm_error = std::abs(probability_sum.value - 1.0);
    if (!std::isfinite(probability_sum.value) || probability_sum.value <= 0 || result.norm_error > 1e-9)
        throw std::runtime_error("Нарушена нормировка вектора амплитуд.");
    std::uniform_real_distribution<double> unit(0.0, 1.0);
    const double threshold = unit(rng) * probability_sum.value;
    CompensatedSum cumulative;
    bool measured = false;
    for (size_t i = 0; i < amplitudes.size(); ++i) {
        cumulative.add(amplitudes[i] * amplitudes[i]);
        if (threshold < cumulative.value) {
            result.measured_index = i;
            result.is_marked = marked[i] != 0;
            measured = true;
            break;
        }
    }
    if (!measured) throw std::runtime_error("Не удалось измерить нормированный вектор амплитуд.");
    result.statevector_elements_processed = states * (2 + 3 * iterations) + result.measured_index + 1;
    if (final_amplitudes) *final_amplitudes = amplitudes;
    deadline.check();
    result.statevector_seconds = deadline.elapsed();
    return result;
}

}
