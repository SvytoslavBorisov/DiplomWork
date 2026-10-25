// Проверяет существование коллизий в редуцированной модели ГОСТ при общей таблице блоков.

#include <algorithm>
#include <array>
#include <cstdint>
#include <iostream>
#include <random>
#include <stdexcept>
#include <string>
#include <unordered_set>
#include <vector>

#include "gost_reduced_model.hpp"

using gost_reduced_model::State;
using gost_reduced_model::compress_with_context;
using gost_reduced_model::make_context;
using gost_reduced_model::random_state;
using gost_reduced_model::reduced_state_from_hex;
using gost_reduced_model::reduced_state_to_hex;
using gost_reduced_model::set_low_sigma_bits;
using gost_reduced_model::required_sigma_low64;

struct StateHasher {
    size_t operator()(const State& value) const noexcept {
        size_t hash = 1469598103934665603ull;
        for (const auto word : value) hash = (hash ^ static_cast<size_t>(word)) * 1099511628211ull;
        return hash;
    }
};

static std::vector<State> random_unique_states(int n, int count, std::mt19937_64& rng) {
    std::vector<State> states;
    std::unordered_set<std::string> seen;
    states.reserve(static_cast<size_t>(count));
    while (static_cast<int>(states.size()) != count) {
        const auto state = random_state(rng);
        const auto hex = reduced_state_to_hex(state, n);
        if (seen.insert(hex).second) states.push_back(reduced_state_from_hex(hex, n));
    }
    return states;
}

static std::vector<State> unique_blocks(
    uint64_t count, std::mt19937_64& rng,
    std::unordered_set<State, StateHasher>& used, uint64_t required, int s
) {
    std::vector<State> blocks;
    blocks.reserve(static_cast<size_t>(count));
    while (blocks.size() < count) {
        auto block = random_state(rng);
        set_low_sigma_bits(block, required, s);
        if (used.insert(block).second) blocks.push_back(block);
    }
    return blocks;
}

int main(int argc, char** argv) {
    try {
        if (argc != 9) throw std::runtime_error("usage: collision_probability_study n k L S rounds s trials seed");
        const int n = std::stoi(argv[1]);
        const int k = std::stoi(argv[2]);
        const uint64_t L = std::stoull(argv[3]);
        const uint64_t S = std::stoull(argv[4]);
        const int rounds = std::stoi(argv[5]);
        const int sigma_bits = std::stoi(argv[6]);
        const int trials = std::stoi(argv[7]);
        const uint64_t seed = std::stoull(argv[8]);
        if (n < 4 || n > 512 || n % 4 != 0 || k < 1 || k > 20 || k > n ||
            rounds < 1 || rounds > 12 || sigma_bits < 0 || sigma_bits > 64 ||
            L == 0 || S == 0 || trials < 1 || (1u << k) > (1ull << std::min(n, 31))) {
            throw std::runtime_error("invalid experiment parameters");
        }
        if ((static_cast<uint64_t>((1u << k) - 1) * L + S) > 5'000'000ull) {
            throw std::runtime_error("trial exceeds 5000000 hash evaluations");
        }
        std::mt19937_64 rng(seed);
        for (int trial = 0; trial < trials; ++trial) {
            const int vertex_count = 1 << k;
            const auto states = random_unique_states(n, vertex_count, rng);
            const uint64_t target_sigma = sigma_bits ? (rng() & (sigma_bits == 64 ? ~uint64_t{0} : ((uint64_t{1} << sigma_bits) - 1))) : 0;
            const auto required = required_sigma_low64(0, target_sigma, sigma_bits);
            std::unordered_set<State, StateHasher> used;
            const auto table = unique_blocks(L, rng, used, required, sigma_bits);
            std::unordered_set<std::string> targets;
            for (int index = 1; index < vertex_count; ++index) {
                const auto context = make_context(states[static_cast<size_t>(index)], 1024, rounds);
                for (const auto& block : table) {
                    targets.insert(reduced_state_to_hex(compress_with_context(block, context), n));
                }
            }
            const auto search = unique_blocks(S, rng, used, required, sigma_bits);
            const auto context = make_context(states[0], 1024, rounds);
            uint64_t marked = 0;
            for (const auto& block : search) {
                if (targets.count(reduced_state_to_hex(compress_with_context(block, context), n))) ++marked;
            }
            std::cout << targets.size() << ' ' << marked << '\n';
        }
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 2;
    }
}
