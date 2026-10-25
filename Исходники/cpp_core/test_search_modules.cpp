#include "quantum_collision_search.hpp"
#include "herding_search.hpp"
#include "quantum_diamond.hpp"
#include "quantum_diamond_bbht.hpp"
#include "herding_link.hpp"
#include "herding_link_bbht.hpp"
#include <iostream>

int search_modules_other_translation_unit();

int main() {
    if (search_modules_other_translation_unit() != 128) return 1;
    std::mt19937_64 rng(42);
    const std::vector<uint8_t> marked{0, 1};
    const auto result = bbht_adaptive::search(marked, rng, [](size_t i) { return i == 1; });
    if (!result.found || result.oracle_queries != result.phase_oracle_queries + result.verification_queries)
        return 2;
    std::cout << "OK\n";
}
