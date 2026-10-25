#pragma once

// EXACT invariant-subspace numerical simulation of Grover iterations.
// A uniform initial vector has one common amplitude on all marked positions
// and one common amplitude on all unmarked positions. Phase and diffusion
// preserve this invariant. This is NOT formula-based probability sampling;
// each Grover iteration is updated numerically. It is not a full dense vector.
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <limits>
#include <random>
#include <stdexcept>
#include <vector>
#include "grover_statevector.hpp"
#include "grover_oracle.hpp"

namespace grover_symmetric {

template<class Oracle>
inline grover_statevector::Result simulate(const Oracle& marked,
                                          uint64_t count_marked, uint64_t iterations,
                                          std::mt19937_64& rng, bool dense_measurement = false) {
    using grover_statevector::Result;
    const auto start = std::chrono::steady_clock::now();
    const uint64_t N=static_cast<uint64_t>(marked.size());
    if(!N || count_marked>N) throw std::runtime_error("Symmetric Grover: invalid marked count");
    if(iterations==std::numeric_limits<uint64_t>::max()) throw std::runtime_error("Grover iterations overflow");
    const uint64_t unmarked=N-count_marked;
    Result out;
    out.iterations=iterations;
    out.oracle_queries=iterations+1;
    out.marked_count=count_marked;
    // Long double protects norm when N >> 1 and very few marked entries.
    const long double a0=1.0L/std::sqrt(static_cast<long double>(N));
    long double a=a0,b=a0;
    for(uint64_t step=0;step<iterations;++step) {
        a=-a; // phase oracle: every marked amplitude is negated
        const long double mean=(static_cast<long double>(count_marked)*a+
                                static_cast<long double>(unmarked)*b)/static_cast<long double>(N);
        a=2.0L*mean-a;
        b=2.0L*mean-b;
    }
    const long double pm=static_cast<long double>(count_marked)*a*a;
    const long double pu=static_cast<long double>(unmarked)*b*b;
    const long double norm=pm+pu;
    out.norm_error=static_cast<double>(std::abs(norm-1.0L));
    if(!std::isfinite(norm) || out.norm_error>1e-9 || norm<=0)
        throw std::runtime_error("Symmetric Grover: vector normalization failed");
    out.success_probability=static_cast<double>(pm/norm);
    std::uniform_real_distribution<double> uniform(0.0,1.0);
    // Select uniformly within the sampled class. For rare marked positions,
    // a single linear scan by rank avoids a huge auxiliary vector of indices.
    // For unmarked samples, rejection of sparse marked candidates is fast.
    std::uniform_int_distribution<uint64_t> index_distribution(0,N-1);
    uint64_t index=0;
    if (dense_measurement) {
        // Сохраняет одно случайное число и накопительное измерение полного вектора через точную функцию распределения.
        const long double threshold=uniform(rng)*norm;
        uint64_t left=0,right=N-1;
        while(left<right) {
            const auto middle=left+(right-left)/2;
            const auto marked_prefix=grover_oracle::prefix_count(marked,static_cast<size_t>(middle));
            const long double cumulative=marked_prefix*a*a+(middle+1-marked_prefix)*b*b;
            if(threshold<cumulative)right=middle;
            else left=middle+1;
        }
        index=left;
    } else {
        const bool choose_marked=count_marked>0 && (unmarked==0 || uniform(rng)<out.success_probability);
        if(choose_marked) {
        std::uniform_int_distribution<uint64_t> rank_distribution(0,count_marked-1);
        auto rank=rank_distribution(rng);
        index=grover_oracle::by_rank(marked,rank);
        } else {
            if(unmarked==0) throw std::runtime_error("Symmetric Grover: no unmarked states");
            do { index=index_distribution(rng); } while(marked[static_cast<size_t>(index)]);
        }
    }
    out.measured_index=static_cast<size_t>(index);
    out.is_marked=marked[static_cast<size_t>(index)]!=0;
    // ACTUAL numerical work over two invariant amplitudes, not an invented dense cost.
    out.statevector_elements_processed=2*(iterations+1);
    out.statevector_seconds=std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count();
    return out;
}
} // namespace grover_symmetric
