#include "bbht_adaptive.hpp"
#include "herding_link_bbht.hpp"
#include "quantum_diamond_bbht.hpp"
#ifdef NDEBUG
#undef NDEBUG
#endif
#include <cassert>
#include <iostream>

int main() {
    try {
        bbht_adaptive::Options options;
        options.max_attempts = 100;
        options.max_oracle_queries = 10000;
        {
            std::vector<uint8_t> marked(32);
            marked[7] = 1;
            std::mt19937_64 rng(123);
            const auto res = bbht_adaptive::search(marked, rng,
                [&](size_t idx) { return idx == 7; }, options);
            assert(res.found && res.measured_index == 7);
            assert(res.attempts == res.verification_queries);
            assert(res.oracle_queries == res.phase_oracle_queries + res.verification_queries);
            assert(res.statevector_iterations == res.phase_oracle_queries);
            assert(res.marked_count_diagnostic == 1);
        }
        {
            std::vector<uint8_t> empty(16);
            std::mt19937_64 rng(22);
            options.max_attempts = 5;
            const auto res = bbht_adaptive::search(empty, rng,
                [](size_t) { return false; }, options);
            assert(!res.found && res.exhausted && res.attempts == 5);
            assert(res.oracle_queries == res.phase_oracle_queries + res.verification_queries);
        }
        options.max_attempts = 100;
        {
            std::vector<uint8_t> marked(64);
            marked[4] = marked[18] = marked[57] = 1;
            std::mt19937_64 first(900), second(900);
            auto verify = [&](size_t j) { return marked[j] == 1; };
            const auto a = bbht_adaptive::search(marked, first, verify, options);
            const auto b = bbht_adaptive::search(marked, second, verify, options);
            assert(a.found == b.found && a.measured_index == b.measured_index);
            assert(a.oracle_queries == b.oracle_queries && a.attempts == b.attempts);
            assert(a.marked_count_diagnostic == 3);
        }
        {
            std::vector<uint8_t> marked(32);
            std::mt19937_64 rng(23);
            bbht_adaptive::Options very_small = options;
            very_small.max_oracle_queries = 1;
            const auto res = bbht_adaptive::search(marked, rng,
                [](size_t) { return false; }, very_small);
            assert(!res.found && res.exhausted && res.oracle_queries <= 1);
        }
        {
            std::vector<uint8_t> marked(8);
            marked[0] = 1;
            std::mt19937_64 rng(9);
            bool threw = false;
            try {
                bbht_adaptive::search(marked, rng,
                    [](size_t) { return false; }, options);
            } catch (const std::runtime_error&) { threw = true; }
            assert(threw);
        }
        {
            const auto prefix = gost_reduced_model::reduced_state_to_hex(State{}, 8);
            std::vector<std::string> targets;
            for (uint64_t i = 0; i < 16; ++i) {
                State state{};
                state[0] = mix64(i + 5);
                targets.push_back(gost_reduced_model::reduced_state_to_hex(state, 8));
            }
            const auto result = herding_link_bbht::find(prefix, targets, 256, 512, 8, 12, 91, 2,
                                                        8, 1, 3, options);
            assert(result.link.found);
            assert(result.search.attempts == result.link.verification_evaluations);
            assert(result.link.oracle_queries == result.search.oracle_queries);
            assert(result.link.simulator_evaluations == 256 + result.search.attempts);
            const auto context = gost_reduced_model::make_context(
                gost_reduced_model::reduced_state_from_hex(prefix, 8), 512, 12);
            assert(gost_reduced_model::compress_with_context(result.link.block, context) == result.link.target);
            assert((result.link.block[7] & 255) == 2);
        }
        {
            std::vector<std::string> states;
            for (uint64_t i = 0; i < 4; ++i) {
                State value{};
                value[0] = mix64(i + 11);
                states.push_back(gost_reduced_model::reduced_state_to_hex(value, 8));
            }
            const auto result = quantum_diamond_bbht::build_layer(states, 32, 129, 2, 1024,
                                                                   8, 12, 17, 2, 8, 1, 3, options);
            assert(result.total_searches == 8);
            assert(result.searches.size() == 8);
            uint64_t recorded_queries = 0;
            uint64_t recorded_marked = 0;
            for (const auto& observation : result.searches) {
                assert(observation.vertex < 4 && observation.repetition < 2);
                assert(observation.oracle_queries == observation.phase_oracle_queries +
                       observation.verification_queries);
                assert(observation.attempts == observation.verification_queries);
                assert(observation.marked_count <= 129);
                recorded_queries += observation.oracle_queries;
                recorded_marked += observation.marked_count;
            }
            assert(recorded_queries + result.layer.qram_entries == result.layer.oracle_queries);
            assert(recorded_marked == result.layer.marked_elements);
            assert(result.layer.simulator_evaluations == 128 + 8 * 129 + result.verification_queries);
            assert(result.layer.oracle_queries == 128 + result.phase_oracle_queries + result.verification_queries);
            assert(result.layer.grover_attempts == result.verification_queries);
            for (const auto& edge : result.layer.edges) {
                assert(edge.left != edge.right);
                const auto left = gost_reduced_model::make_context(
                    gost_reduced_model::reduced_state_from_hex(states[edge.left], 8), 1024, 12);
                const auto right = gost_reduced_model::make_context(
                    gost_reduced_model::reduced_state_from_hex(states[edge.right], 8), 1024, 12);
                assert(gost_reduced_model::compress_with_context(edge.left_block, left) == edge.common);
                assert(gost_reduced_model::reduced_state_to_hex(
                    gost_reduced_model::compress_with_context(edge.right_block, right), 8) ==
                    gost_reduced_model::reduced_state_to_hex(edge.common, 8));
                assert((edge.left_block[7] & 255) == 2 && (edge.right_block[7] & 255) == 2);
            }
        }
        std::cout << "OK BBHT_TESTS_PASS\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "BBHT_TESTS_FAIL: " << error.what() << '\n';
        return 1;
    }
}
