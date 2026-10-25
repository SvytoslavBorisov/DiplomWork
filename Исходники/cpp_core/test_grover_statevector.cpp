#include "grover_statevector.hpp"
#include "grover_analytic.hpp"
#include <iostream>

const void* other_statevector_address();

static void require(bool condition, const char* message) {
    if (!condition) throw std::runtime_error(message);
}

int main() {
    using namespace grover_statevector;
    require(other_statevector_address() == reinterpret_cast<const void*>(&apply_diffusion), "ODR mismatch");
    std::vector<double> phase(8, 1.0 / std::sqrt(8.0));
    std::vector<uint8_t> oracle(8, 0); oracle[3] = 1;
    const double initial = phase[0];
    apply_phase_oracle(phase, oracle);
    require(phase[3] == -initial && phase[0] == initial, "phase oracle mismatch");
    apply_diffusion(phase);
    require(std::abs(phase[3] - 2.5 * initial) < 1e-14 && std::abs(phase[0] - .5 * initial) < 1e-14, "diffusion mismatch");
    uint64_t cases = 0;
    for (auto pair : {std::pair<size_t, size_t>{8, 1}, {16, 1}, {16, 4}, {32, 0}, {32, 32}, {256, 1}, {1024, 1}, {1024, 2}, {1024, 4}}) {
        for (uint64_t iterations : {uint64_t{0}, uint64_t{1}, grover_analytic::optimal_grover_iterations(pair.first, 1), uint64_t{25}}) {
            std::vector<uint8_t> marked(pair.first, 0);
            for (size_t i = 0; i < pair.second; ++i) marked[i] = 1;
            std::mt19937_64 rng(51), replay(51);
            std::vector<double> amplitudes;
            const auto result = simulate_grover_statevector(marked, iterations, rng, &amplitudes);
            const auto repeated = simulate_grover_statevector(marked, iterations, replay);
            require(result.measured_index == repeated.measured_index, "seed mismatch");
            require(result.marked_count == pair.second && result.iterations == iterations && result.oracle_queries == iterations + 1, "counter mismatch");
            require(result.is_marked == bool(marked[result.measured_index]), "unmarked measurement converted into success");
            const double theory = grover_analytic::grover_success_probability_analytic(pair.first, pair.second, iterations);
            require(std::abs(result.success_probability - theory) < 1e-11 && result.norm_error < 1e-11, "probability or normalization mismatch");
            double norm = 0;
            for (double amplitude : amplitudes) norm += amplitude * amplitude;
            require(std::abs(norm - 1) < 1e-11, "amplitude norm mismatch");
            require(result.statevector_elements_processed == pair.first * (2 + 3 * iterations) + result.measured_index + 1, "element count mismatch");
            if (!pair.second) require(!result.is_marked && result.success_probability == 0, "empty oracle mismatch");
            ++cases;
        }
    }
    size_t successes = 0;
    std::vector<uint8_t> marked(16, 0); marked[0] = marked[4] = marked[8] = marked[12] = 1;
    for (uint64_t seed = 0; seed < 1000; ++seed) {
        std::mt19937_64 rng(seed);
        successes += simulate_grover_statevector(marked, 0, rng).is_marked;
    }
    require(successes > 200 && successes < 300, "empirical sampling mismatch");
    bool refused = false;
    try { check_resources(1048577, 0); } catch (const std::runtime_error&) { refused = true; }
    require(refused, "state limit not enforced");
    refused = false;
    try { check_resources(1048576, 804); } catch (const std::runtime_error&) { refused = true; }
    require(refused, "work limit not enforced");
    std::cout << "STATEVECTOR PASS: " << cases << " cases, 1000 measurements, ODR, limits\n";
}
