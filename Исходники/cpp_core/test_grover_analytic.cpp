#ifdef GROVER_TEST_CORE_SOURCE
#define main gost_core_command_main
#include GROVER_TEST_CORE_SOURCE
#undef main
#else
#include "grover_analytic.hpp"
#include "grover_analytic.hpp"
using namespace grover_analytic;
uint64_t grover_iterations_other_tu(uint64_t, uint64_t);
double grover_probability_other_tu(uint64_t, uint64_t, uint64_t);
#endif

#include <array>
#include <cstring>
#include <iostream>
#include <limits>

static uint64_t digest = 14695981039346656037ULL;
static void record(uint64_t value) {
    for (int byte = 0; byte < 8; ++byte) {
        digest ^= (value >> (8 * byte)) & 255;
        digest *= 1099511628211ULL;
    }
}
static void record(double value) {
    uint64_t bits = 0;
    static_assert(sizeof(bits) == sizeof(value));
    std::memcpy(&bits, &value, sizeof(bits));
    record(bits);
}
static void require(bool valid, const char* message) {
    if (!valid) throw std::runtime_error(message);
}

int main() {
    try {
        const std::array<uint64_t, 4> domains{8, 16, 256, 1024};
        const std::array<uint64_t, 4> expected{2, 3, 12, 25};
        for (size_t i = 0; i < domains.size(); ++i) {
            require(optimal_grover_iterations(domains[i], 1) == expected[i], "iteration rounding");
        }
        size_t probabilities = 0, measurements = 0, mismatches = 0;
        for (uint64_t n : {uint64_t{0}, uint64_t{1}, uint64_t{8}, uint64_t{16}, uint64_t{256}, uint64_t{1024}}) {
            require(optimal_grover_iterations(n, 0) == 0, "empty marked set iterations");
            require(optimal_grover_iterations(n, n) == 0, "all marked iterations");
            for (uint64_t count : {uint64_t{0}, std::min(uint64_t{1}, n), n / 2, n}) {
                const uint64_t iterations = optimal_grover_iterations(n, count);
                record(iterations);
#ifndef GROVER_TEST_CORE_SOURCE
                require(iterations == grover_iterations_other_tu(n, count), "iterations in second TU");
#endif
                for (uint64_t steps : {uint64_t{0}, uint64_t{1}, iterations, uint64_t{100}}) {
                    const double probability = grover_success_probability_analytic(n, count, steps);
                    require(probability >= 0 && probability <= 1, "probability range");
                    if (n == 0 || count == 0) require(probability == 0, "empty probability");
#ifndef GROVER_TEST_CORE_SOURCE
                    require(probability == grover_probability_other_tu(n, count, steps), "probability in second TU");
#endif
                    record(probability);
                    ++probabilities;
                }
                std::vector<uint8_t> marked(static_cast<size_t>(n), 0);
                for (size_t i = 0; i < count; ++i) marked[i] = 1;
                for (uint64_t seed = 0; seed < 256; ++seed) {
                    std::mt19937_64 array_rng(seed), predicate_rng(seed), repeated_rng(seed);
                    uint64_t array_queries = 37, predicate_queries = 37, repeated_queries = 37;
                    const size_t a = simulate_fixed_measurement(marked, array_rng, array_queries);
                    const size_t b = simulate_fixed_measurement(marked.size(), count,
                        [&](size_t index) { return marked[index] != 0; }, predicate_rng, predicate_queries);
                    const size_t repeated = simulate_fixed_measurement(marked, repeated_rng, repeated_queries);
                    require(a == b && a == repeated, "overloads and seed reproduction");
                    require(a == n || (a < marked.size() && marked[a]), "measured index");
                    require(array_queries == 37 + optimal_grover_iterations(n, 1) + 1, "fixed one-solution queries");
                    require(array_queries == predicate_queries && array_queries == repeated_queries, "overload queries");
                    const uint64_t next = array_rng();
                    require(next == predicate_rng() && next == repeated_rng(), "RNG stream preservation");
                    record(static_cast<uint64_t>(a)); record(array_queries); record(next);
                    ++measurements;
                }
            }
        }
        // Сохраняет исходное исключение при успешном измерении отсутствующего помеченного элемента.

        for (uint64_t seed = 0; seed < 256; ++seed) {
            std::mt19937_64 rng(seed), reference(seed);
            std::uniform_real_distribution<double> unit(0.0, 1.0);
            const bool success = unit(reference) < grover_success_probability_analytic(8, 1, 2);
            if (success) {
                std::uniform_int_distribution<uint64_t> choose(0, 0);
                (void)choose(reference);
            }
            uint64_t queries = 5;
            bool rejected = false;
            size_t result = 8;
            try { result = simulate_fixed_measurement(size_t{8}, uint64_t{1}, [](size_t) { return false; }, rng, queries); }
            catch (const std::runtime_error&) { rejected = true; }
            require(rejected == success && result == 8, "predicate count mismatch behavior");
            require(queries == 8 && rng() == reference(), "mismatch queries and RNG");
            record(static_cast<uint64_t>(rejected)); record(queries);
            mismatches += rejected;
        }
        require(mismatches > 0, "inconsistency fixture reached no exceptions");
        std::cout << "GROVER PASS probabilities=" << probabilities
                  << " measurements=" << measurements << " mismatches=" << mismatches
                  << " digest=" << std::hex << digest << '\n';
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
