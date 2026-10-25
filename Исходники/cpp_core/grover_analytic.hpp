#pragma once

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <random>
#include <stdexcept>
#include <vector>

namespace grover_analytic {

using std::size_t;
using std::uint8_t;
using std::uint64_t;

inline uint64_t optimal_grover_iterations(uint64_t domain_size, uint64_t marked_count) {
    if (domain_size == 0 || marked_count == 0 || marked_count == domain_size) return 0;
    const double theta = std::asin(std::sqrt(
        static_cast<double>(marked_count) / static_cast<double>(domain_size)));
    const double raw = std::acos(-1.0) / (4.0 * theta) - 0.5;
    return static_cast<uint64_t>(std::max<long long>(0, std::llround(raw)));
}

inline double grover_success_probability_analytic(
    uint64_t domain_size,
    uint64_t marked_count,
    uint64_t iterations
) {
    if (domain_size == 0 || marked_count == 0) return 0.0;
    const double theta = std::asin(std::sqrt(
        static_cast<double>(marked_count) / static_cast<double>(domain_size)));
    const double angle = static_cast<double>(2 * iterations + 1) * theta;
    return std::clamp(std::sin(angle) * std::sin(angle), 0.0, 1.0);
}

// Моделирует измерение с фиксированным бюджетом для одного решения и равными амплитудами помеченных состояний.

inline size_t simulate_fixed_measurement(const std::vector<uint8_t>& marked,
                                         std::mt19937_64& rng, uint64_t& queries) {
    const size_t n = marked.size();
    const uint64_t count = std::count(marked.begin(), marked.end(), uint8_t{1});
    const uint64_t iterations = optimal_grover_iterations(n, 1);
    queries += iterations + 1;
    std::uniform_real_distribution<double> unit(0.0, 1.0);
    const double probability = grover_success_probability_analytic(n, count, iterations);
    if (!count || unit(rng) >= probability) return n;
    std::uniform_int_distribution<uint64_t> choose(0, count - 1);
    uint64_t rank = choose(rng);
    for (size_t i = 0; i < n; ++i) if (marked[i] && rank-- == 0) return i;
    return n;
}

// Моделирует то же измерение через предикат помеченных элементов.
template<class Predicate>
inline size_t simulate_fixed_measurement(size_t n,uint64_t count,Predicate marked,
    std::mt19937_64& rng,uint64_t& queries) {
    const uint64_t iterations=optimal_grover_iterations(n,1);
    queries+=iterations+1;
    std::uniform_real_distribution<double> unit(0.0,1.0);
    const double probability=grover_success_probability_analytic(n,count,iterations);
    if(!count || unit(rng)>=probability)return n;
    std::uniform_int_distribution<uint64_t> choose(0,count-1);
    uint64_t rank=choose(rng);
    for(size_t i=0;i<n;++i)if(marked(i) && rank--==0)return i;
    throw std::runtime_error("marked count / predicate inconsistency");
}

}
