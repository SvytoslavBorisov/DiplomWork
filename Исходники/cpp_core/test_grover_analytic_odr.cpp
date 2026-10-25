#include "grover_analytic.hpp"

std::uint64_t grover_iterations_other_tu(std::uint64_t n, std::uint64_t count) {
    return grover_analytic::optimal_grover_iterations(n, count);
}

double grover_probability_other_tu(std::uint64_t n, std::uint64_t count, std::uint64_t iterations) {
    return grover_analytic::grover_success_probability_analytic(n, count, iterations);
}
