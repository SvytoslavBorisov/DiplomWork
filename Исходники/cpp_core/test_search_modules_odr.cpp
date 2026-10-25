#include "herding_link_bbht.hpp"
#include "herding_search.hpp"
#include "quantum_diamond_bbht.hpp"
#include "quantum_collision_search.hpp"

int search_modules_other_translation_unit() {
    return static_cast<int>(bbht_adaptive::Options{}.max_attempts);
}
