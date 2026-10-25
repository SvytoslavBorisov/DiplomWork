#pragma once

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <limits>
#include <random>
#include <stdexcept>
#include <vector>
#include <ostream>
#include <iomanip>
#include "grover_statevector.hpp"
#include "bbht_dense_statevector.hpp"
#include "grover_symmetric.hpp"
#include "grover_analytic.hpp"

// Реализует ограниченный адаптивный поиск BBHT без предварительного знания числа решений.
namespace bbht_adaptive {

inline constexpr const char* search_protocol = "fixed-single-bbht-auto-v1";

// Ограничивает эвристический резерв после роста окна до порядка квадратного корня из S.
inline uint64_t effective_max_attempts(uint64_t states, double growth, uint64_t cap = 128) {
    if (!states || !cap || !std::isfinite(growth) || !(growth > 1.0 && growth < 4.0/3.0))
        throw std::runtime_error("BBHT: неверное пространство, коэффициент роста или верхний предел попыток.");
    if (cap <= 8) return cap;
    const long double steps = 0.5L * std::log(static_cast<long double>(states)) /
        std::log1p(static_cast<long double>(growth)-1.0L);
    if (steps >= static_cast<long double>(cap-8)) return cap;
    return std::min(cap, static_cast<uint64_t>(std::ceil(steps)) + uint64_t{8});
}

struct Options {
    double growth = 1.2;
    uint64_t max_attempts = 128;
    uint64_t max_oracle_queries = 100000;
    uint64_t dense_max_states = 8192;
    double max_stage_seconds = 0.0;  // 0 = unlimited
};

struct Result {
    bool found = false;
    size_t measured_index = 0;
    uint64_t attempts = 0;
    uint64_t failures = 0;
    uint64_t oracle_queries = 0;
    uint64_t phase_oracle_queries = 0;
    uint64_t verification_queries = 0;
    uint64_t statevector_iterations = 0;
    uint64_t statevector_elements_processed = 0;
    uint64_t marked_count_diagnostic = 0;
    double success_probability_sum = 0.0;
    double norm_error_max = 0.0;
    double statevector_seconds = 0.0;
    bool exhausted = false;
    uint64_t search_messages = 0;
    double growth = 1.2;
    uint64_t effective_max_attempts = 0;
    const char* attempt_policy = "bbht_auto";
    const char* stop_reason = "attempt_limit";
};

// Записывает фактическую политику и причину остановки каждого поиска без изменения счётчиков.
inline void write_diagnostics(std::ostream& stream, const std::vector<Result>& searches) {
    const auto precision = stream.precision();
    stream << std::setprecision(17);
    stream << " SEARCH " << search_protocol << ' ' << searches.size();
    for (const auto& search : searches)
        stream << ' ' << search.attempt_policy << ' ' << search.search_messages << ' '
               << search.growth << ' ' << search.effective_max_attempts << ' '
               << search.attempts << ' ' << search.failures << ' ' << search.stop_reason;
    stream.precision(precision);
}

// Выполняет единственное измерение фиксированного Гровера независимо от ограничений BBHT.
template<class Oracle, class Verifier>
inline Result fixed_single(const Oracle& marked, std::mt19937_64& rng, Verifier&& verify) {
    if (marked.empty()) throw std::runtime_error("Фиксированный Гровер: пространство поиска пусто.");
    const auto iterations = grover_analytic::optimal_grover_iterations(marked.size(), 1);
    const auto simulation = marked.size() <= grover_oracle::dense_max_states
        ? grover_statevector::simulate_grover_statevector(marked, iterations, rng)
        : grover_symmetric::simulate(marked, grover_oracle::count(marked), iterations, rng, true);
    const bool accepted = static_cast<bool>(verify(simulation.measured_index));
    if (accepted != simulation.is_marked)
        throw std::runtime_error("Фиксированный Гровер: результат ГОСТ не совпал с фазовым оракулом.");
    Result result;
    result.found = accepted;
    result.measured_index = simulation.measured_index;
    result.attempts = 1;
    result.failures = accepted ? 0 : 1;
    result.oracle_queries = simulation.oracle_queries;
    result.phase_oracle_queries = simulation.iterations;
    result.verification_queries = 1;
    result.statevector_iterations = simulation.iterations;
    result.statevector_elements_processed = simulation.statevector_elements_processed;
    result.marked_count_diagnostic = simulation.marked_count;
    result.success_probability_sum = simulation.success_probability;
    result.norm_error_max = simulation.norm_error;
    result.statevector_seconds = simulation.statevector_seconds;
    result.exhausted = !accepted;
    result.search_messages = marked.size();
    result.effective_max_attempts = 1;
    result.attempt_policy = "fixed_single";
    result.stop_reason = accepted ? "found" : "unmarked_measurement";
    return result;
}

// Проверка выполняется внешним предикатом на реальном результате функции сжатия.
template<class Oracle, class Verifier>
inline Result search(const Oracle& marked, std::mt19937_64& rng,
                     Verifier&& verify, const Options& options = {}) {
    if (marked.empty()) throw std::runtime_error("BBHT: пространство поиска пусто.");
    if (!(options.growth > 1.0 && options.growth < 4.0 / 3.0) || !std::isfinite(options.growth) ||
        !options.max_attempts || !options.max_oracle_queries)
        throw std::runtime_error("BBHT: неверные ограничения или коэффициент роста.");
    const bool dense = marked.size() <= options.dense_max_states;
    if(dense) grover_statevector::check_resources(marked.size(), 0);
    const auto M=grover_oracle::count(marked);
    Result result;
    result.search_messages = marked.size();
    result.growth = options.growth;
    result.effective_max_attempts = effective_max_attempts(marked.size(), options.growth, options.max_attempts);
    double width = 1.0;
    const double maximum = std::max(1.0, std::sqrt(static_cast<double>(marked.size())));
    for (uint64_t attempt = 0; attempt < result.effective_max_attempts; ++attempt) {
        const uint64_t window = std::max<uint64_t>(1, static_cast<uint64_t>(std::ceil(width)));
        std::uniform_int_distribution<uint64_t> choose(0, window - 1);
        const uint64_t iterations = choose(rng);
        if (iterations + 1 > options.max_oracle_queries - result.oracle_queries) {
            result.exhausted = true;
            result.stop_reason = "query_limit";
            return result;
        }
        const auto sim = dense ? bbht_dense_statevector::simulate(marked, iterations, rng)
                               : grover_symmetric::simulate(marked, M, iterations, rng);
        const bool accepted = static_cast<bool>(verify(sim.measured_index));
        if (accepted != sim.is_marked)
            throw std::runtime_error("BBHT: проверка через ГОСТ не совпала с фазовым оракулом.");
        ++result.attempts;
        result.oracle_queries += sim.oracle_queries;
        result.phase_oracle_queries += sim.iterations;
        ++result.verification_queries;
        result.statevector_iterations += sim.iterations;
        result.statevector_elements_processed += sim.statevector_elements_processed;
        result.marked_count_diagnostic = sim.marked_count;
        result.success_probability_sum += sim.success_probability;
        result.norm_error_max = std::max(result.norm_error_max, sim.norm_error);
        result.statevector_seconds += sim.statevector_seconds;
        if (accepted) {
            result.found = true;
            result.stop_reason = "found";
            result.measured_index = sim.measured_index;
            return result;
        }
        ++result.failures;
        width = std::min(maximum, width * options.growth);
    }
    result.exhausted = true;
    return result;
}

// Повторяет фиксированный поиск Гровера на той же таблице решений для контрольного сравнения.
template<class Oracle, class Verifier>
inline Result fixed_repeated(const Oracle& marked, uint64_t iterations,
                             std::mt19937_64& rng, Verifier&& verify,
                             const Options& options = {}) {
    if (marked.empty() || !options.max_attempts || !options.max_oracle_queries)
        throw std::runtime_error("Fixed Grover: неверные параметры.");
    const bool dense = marked.size() <= options.dense_max_states;
    if(dense) grover_statevector::check_resources(marked.size(), 0);
    const auto M=grover_oracle::count(marked);
    Result result;
    for (uint64_t attempt = 0; attempt < options.max_attempts; ++attempt) {
        if (iterations >= options.max_oracle_queries - result.oracle_queries) {
            result.exhausted = true;
            return result;
        }
        const auto sim = dense ? bbht_dense_statevector::simulate(marked, iterations, rng)
                               : grover_symmetric::simulate(marked, M, iterations, rng);
        const bool accepted = static_cast<bool>(verify(sim.measured_index));
        if (accepted != sim.is_marked)
            throw std::runtime_error("Fixed Grover: проверка через ГОСТ не совпала с оракулом.");
        ++result.attempts;
        result.oracle_queries += sim.oracle_queries;
        result.phase_oracle_queries += sim.iterations;
        ++result.verification_queries;
        result.statevector_iterations += sim.iterations;
        result.statevector_elements_processed += sim.statevector_elements_processed;
        result.marked_count_diagnostic = sim.marked_count;
        result.success_probability_sum += sim.success_probability;
        result.norm_error_max = std::max(result.norm_error_max, sim.norm_error);
        result.statevector_seconds += sim.statevector_seconds;
        if (accepted) {
            result.found = true;
            result.measured_index = sim.measured_index;
            return result;
        }
        ++result.failures;
    }
    result.exhausted = true;
    return result;
}

} // namespace bbht_adaptive
