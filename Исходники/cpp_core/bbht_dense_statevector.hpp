#pragma once

// Dedicated dense Grover simulator for the independent BBHT CLI.
// Identical phase, diffusion and measurement operations to grover_statevector,
// but without grover_statevector::Deadline's hard-coded 30-second watchdog.
// The main application's grover_statevector.hpp is not modified.

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <limits>
#include <random>
#include <stdexcept>
#include <vector>
#include "grover_statevector.hpp"

namespace bbht_dense_statevector {

inline grover_statevector::Result simulate(const std::vector<uint8_t>& marked,
                                          uint64_t iterations,
                                          std::mt19937_64& rng) {
    using namespace grover_statevector;
    const uint64_t states = static_cast<uint64_t>(marked.size());
    check_resources(states, iterations);
    const auto start = std::chrono::steady_clock::now();
    Result result;
    result.iterations = iterations;
    result.oracle_queries = iterations + 1;
    for (const uint8_t flag : marked) {
        if (flag > 1) throw std::runtime_error("BBHT dense: invalid oracle mask");
        result.marked_count += flag;
    }
    std::vector<double> amplitudes(static_cast<size_t>(states),
                                   1.0 / std::sqrt(static_cast<double>(states)));
    for (uint64_t iteration = 0; iteration < iterations; ++iteration) {
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
    if (!std::isfinite(probability_sum.value) || probability_sum.value <= 0 ||
        result.norm_error > 1e-9)
        throw std::runtime_error("BBHT dense: invalid statevector normalization");
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
    if (!measured) throw std::runtime_error("BBHT dense: statevector measurement failed");
    // Same accounting as the production dense simulator.
    result.statevector_elements_processed = states * (2 + 3 * iterations) +
                                            result.measured_index + 1;
    result.statevector_seconds =
        std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count();
    return result;
}

} // namespace bbht_dense_statevector
