#include "quantum_diamond.hpp"

uint64_t quantum_other_tu_queries() {
    requested_qram = "u64";
    return quantum_diamond::build_quantum_layer(
        {"00", "40", "80", "c0"}, 32, 129, 2, 1024, 8, 12, 731, 4).oracle_queries;
}
