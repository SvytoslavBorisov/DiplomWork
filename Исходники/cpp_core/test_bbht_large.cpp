#include <cmath>
#include <cstdint>
#include <iostream>
#include <random>
#include <stdexcept>
#include <vector>
#include "grover_symmetric.hpp"
#include "bbht_adaptive.hpp"

static void ensure(bool ok,const char* why) { if(!ok)throw std::runtime_error(why); }
int main() {
    try {
        for(const size_t N:{size_t{8},size_t{29},size_t{256},size_t{1024}}) {
            for(const size_t M:{size_t{0},size_t{1},size_t{2},size_t{5},N}) {
                if(M>N) continue;
                std::vector<uint8_t> mask(N,0);
                for(size_t i=0;i<M;++i)mask[i*(N/M ? N/M : 1)]=1;
                grover_oracle::MarkedSpace sparse(N,0);
                for(size_t i=0;i<N;++i)if(mask[i])sparse.add(i);
                for(uint64_t iterations: {uint64_t{0},uint64_t{1},uint64_t{2},uint64_t{3},uint64_t{7},uint64_t{19}}) {
                    std::mt19937_64 a(14),b(14),c(14),d(14);
                    const auto dense=grover_statevector::simulate_grover_statevector(mask,iterations,a);
                    const auto sym=grover_symmetric::simulate(mask,M,iterations,b);
                    const auto compact=grover_symmetric::simulate(sparse,M,iterations,c);
                    const auto same_measurement=grover_symmetric::simulate(sparse,M,iterations,d,true);
                    ensure(same_measurement.measured_index==dense.measured_index && a()==d(),
                           "Разреженное измерение фиксированного Гровера изменило seed или число случайных выборок");
                    ensure(compact.measured_index==sym.measured_index && compact.is_marked==sym.is_marked,
                           "Разреженный оракул изменил измерение или порядок случайных чисел");
                    ensure(compact.success_probability==sym.success_probability && compact.oracle_queries==sym.oracle_queries,
                           "Разреженный оракул изменил амплитуды или запросы");
                    ensure(std::abs(dense.success_probability-sym.success_probability)<1e-11,
                           "Two-amplitude numerical Grover differs from full statevector");
                    ensure(sym.norm_error<1e-9,"Numerical two-amplitude normalization failed");
                    ensure(sym.oracle_queries==dense.oracle_queries,"Query count mismatch");
                }
            }
        }
        // Tests larger than the hardcoded million-element dense-statevector ceiling.
        const size_t N=2097152;
        std::vector<uint8_t> mask(N,0);
        mask[123]=1;
        std::mt19937_64 rng(27);
        const auto large=grover_symmetric::simulate(mask,1,1100,rng);
        ensure(large.success_probability>0.9,"Large-space numerical amplification failed");
        bbht_adaptive::Options opts;
        opts.max_attempts=96;
        opts.max_oracle_queries=10000;
        opts.dense_max_states=256;
        std::vector<uint8_t> small(1024,0);
        small[313]=1;
        auto result=bbht_adaptive::search(small,rng,[&](size_t i){return small[i]!=0;},opts);
        ensure(result.found && result.measured_index==313,"Adaptive search failed with symmetric simulator");
        // Проверяет огромные пространства без выделения маски по числу кандидатов.
        for(uint64_t states:{uint64_t{1}<<36,uint64_t{1}<<40,uint64_t{1}<<44}) {
            grover_oracle::MarkedSpace sparse(states,0);
            sparse.add(states-17);
            std::mt19937_64 large_rng(51);
            const auto numerical=grover_symmetric::simulate(sparse,1,10000,large_rng);
            ensure(numerical.norm_error<1e-9 && numerical.marked_count==1,
                   "Нарушена нормировка большого разреженного пространства");
        }
        grover_oracle::MarkedSpace sparse_small(1024,0);
        sparse_small.add(313);
        std::mt19937_64 old_rng(42),sparse_rng(42);
        const auto old_search=bbht_adaptive::search(small,old_rng,[&](size_t i){return small[i]!=0;},opts);
        const auto sparse_search=bbht_adaptive::search(sparse_small,sparse_rng,[&](size_t i){return sparse_small[i];},opts);
        ensure(old_search.measured_index==sparse_search.measured_index &&
               old_search.oracle_queries==sparse_search.oracle_queries &&
               old_search.failures==sparse_search.failures && old_search.attempts==sparse_search.attempts,
               "Разреженный BBHT изменил последовательность попыток или учёт неудач");
        std::cout<<"PASS: dense equivalence, large numerical symmetry, adaptive search\n";
        return 0;
    } catch(const std::exception& e) {
        std::cerr<<"FAIL: "<<e.what()<<'\n';return 1;
    }
}
