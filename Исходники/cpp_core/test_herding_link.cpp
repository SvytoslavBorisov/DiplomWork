#include "herding_link.hpp"

std::uintptr_t herding_link_odr_address();

static void require(bool value, const char* message) {
    if (!value) throw std::runtime_error(message);
}

int main() {
    using namespace herding_link;
    using gost_reduced_model::reduced_state_to_hex;
    require(herding_link_odr_address() == reinterpret_cast<std::uintptr_t>(&find_link), "ODR address");
    has_requested_seed = true;
    requested_seed = 11;
    for (int n : {12, 64, 68, 512}) {
        for (int s : {0, 4, 64}) {
            const uint64_t current = s ? 3 : 0, target = s ? 7 : 0;
            const uint64_t low = required_sigma_low64(current, target, s);
            const State prefix = reduced_state_from_hex(std::string(n / 4, '1'), n);
            const auto context = make_context(prefix, 512, 1);
            for (const std::string rng_name : {"mt19937", "xoshiro256ss"}) {
                requested_rng = rng_name;
                std::mt19937_64 rng(mix64(requested_seed));
                auto fast_rng = optional_candidate_rng();
                std::vector<State> candidates(8);
                fill_candidates(candidates, rng, fast_rng.get(), low, s);
                const auto expected = compress_with_context(candidates.front(), context);
                std::vector<std::string> targets{reduced_state_to_hex(expected, n)};
                for (int threads : {1, 4}) {
                    const auto result = find_link(reduced_state_to_hex(prefix, n), 512, n, 1, 8, threads, targets, s, current, target);
                    require(result.ok && result.block == candidates.front() && result.queries == 8, "seeded classic result");
                    require(compress_with_context(result.block, context) == result.state, "classic independent replay");
                    require((result.block[7] & gost_reduced_model::sigma_mask64(s)) == low, "classic Sigma bits");
                }
            }
            std::vector<std::string> quantum_targets;
            for (uint64_t index = 0; index < 32; ++index) {
                State block{};
                block[0] = mix64(index + 11);
                for (size_t word = 1; word < block.size(); ++word)
                    block[word] = mix64(index ^ 11 ^ (0x9e3779b97f4a7c15ULL * static_cast<uint64_t>(word)));
                set_low_sigma_bits(block, low, s);
                quantum_targets.push_back(reduced_state_to_hex(compress_with_context(block, context), n));
            }
            QuantumLinkResult previous;
            for (int threads : {1, 4}) {
                const auto result = find_quantum_link(reduced_state_to_hex(prefix, n), quantum_targets, 32, 512, n, 1, 11, threads, s, current, target);
                require(result.found && result.marked_count == 32 && result.simulator_evaluations == 33, "quantum marked space");
                require(result.oracle_queries == optimal_grover_iterations(32, 1) + 1, "quantum oracle charge");
                require(compress_with_context(result.block, context) == result.target, "quantum independent replay");
                require((result.block[7] & gost_reduced_model::sigma_mask64(s)) == low, "quantum Sigma bits");
                if (threads == 4)
                    require(result.block == previous.block && result.target == previous.target, "quantum worker reproduction");
                previous = result;
            }
        }
    }
    std::cout << "OK HERDING_LINK_AND_ODR_PASS\n";
}
