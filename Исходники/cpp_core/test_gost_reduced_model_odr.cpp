#include "gost_reduced_model.hpp"

const gost_reduced_model::LpsTable* reduced_model_table_from_other_tu() {
    return &gost_reduced_model::LPS_TABLE;
}

gost_reduced_model::State reduced_model_compress_from_other_tu(
    const gost_reduced_model::State& m, const gost_reduced_model::State& h,
    uint64_t N, int rounds) {
    return gost_reduced_model::compress_state(m, h, N, rounds);
}
