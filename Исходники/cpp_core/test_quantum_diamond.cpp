#ifdef QUANTUM_TEST_CORE_SOURCE
#define main gost_core_command_main
#include QUANTUM_TEST_CORE_SOURCE
#undef main
#else
#include "quantum_diamond.hpp"
#include "quantum_diamond.hpp"
using namespace quantum_diamond;
uint64_t quantum_other_tu_queries();
#endif

#include <iomanip>

static uint64_t digest = 14695981039346656037ULL;
static void record(uint64_t value) {
    for (int byte = 0; byte < 8; ++byte) {
        digest ^= (value >> (8 * byte)) & 255;
        digest *= 1099511628211ULL;
    }
}
static void record(const State& state) {
    for (uint64_t word : state) record(word);
}
static void require(bool condition, const char* message) {
    if (!condition) throw std::runtime_error(message);
}

int main() {
    try {
        uint64_t cases = 0, edges = 0;
        for (int n : {4, 8, 12, 32, 64, 68}) {
            std::vector<std::string> states;
            for (uint64_t vertex = 0; vertex < 4; ++vertex) {
                State state{};
                state[0] = mix64(vertex + 1);
                states.push_back(gost_reduced_model::reduced_state_to_hex(state, n));
            }
            for (int s : {0, 1, 8, 16, 24, 32, 64}) {
                for (uint64_t seed : {0ULL, 11ULL, 731ULL}) {
                    for (const char* qram : {"generic", "u64"}) {
                        requested_qram = qram;
                        for (int threads : {1, 4}) {
                            const auto layer = build_quantum_layer(
                                states, 32, 129, 2, 1024, n, 12, seed, threads, s, 3, 7);
                            record(layer.oracle_queries);
                            record(layer.simulator_evaluations);
                            record(layer.qram_entries);
                            record(layer.grover_successes);
                            record(layer.edges.size());
                            require(layer.qram_entries == 128, "qRAM accounting");
                            require(layer.simulator_evaluations == 128 + 4 * 2 * (129 + 1), "hash accounting");
                            for (const auto& edge : layer.edges) {
                                require(edge.left != edge.right && edge.left < 4 && edge.right < 4, "cross-vertex edge");
                                const auto left = gost_reduced_model::make_context(
                                    gost_reduced_model::reduced_state_from_hex(states[edge.left], n), 1024, 12);
                                const auto right = gost_reduced_model::make_context(
                                    gost_reduced_model::reduced_state_from_hex(states[edge.right], n), 1024, 12);
                                const auto output_left = gost_reduced_model::compress_with_context(edge.left_block, left);
                                const auto output_right = gost_reduced_model::compress_with_context(edge.right_block, right);
                                require(output_left == edge.common, "left edge replay");
                                require(gost_reduced_model::reduced_state_to_hex(output_right, n) ==
                                        gost_reduced_model::reduced_state_to_hex(edge.common, n), "right edge replay");
                                const uint64_t mask = gost_reduced_model::sigma_mask64(s);
                                require(((3 + edge.left_block[7]) & mask) == (7 & mask), "left Sigma");
                                require(((3 + edge.right_block[7]) & mask) == (7 & mask), "right Sigma");
                                record(edge.left); record(edge.right);
                                record(edge.left_block); record(edge.right_block); record(edge.common);
                                ++edges;
                            }
                            ++cases;
                        }
                    }
                }
            }
        }
        uint64_t exceptions = 0;
        for (int invalid : {0, 1, 2}) {
            try {
                build_quantum_layer(invalid == 0 ? std::vector<std::string>{"00"} :
                    std::vector<std::string>{"00", "40", "80", "c0"},
                    invalid == 1 ? 0 : 32, 129, invalid == 2 ? 1 : 2,
                    1024, 8, 12, 731, 4);
            } catch (const std::runtime_error&) { ++exceptions; }
        }
        require(exceptions == 3, "invalid layer arguments");
#ifndef QUANTUM_TEST_CORE_SOURCE
        requested_qram = "generic";
        require(quantum_other_tu_queries() == build_quantum_layer(
            {"00", "40", "80", "c0"}, 32, 129, 2, 1024, 8, 12, 731, 4).oracle_queries,
            "other translation unit");
        require(requested_qram == "u64", "shared inline configuration");
#endif
        std::cout << "OK QUANTUM_DIAMOND_TESTS_PASS cases=" << cases << " edges=" << edges
                  << " exceptions=" << exceptions << " digest=" << std::hex << digest << '\n';
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
