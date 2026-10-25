#include <cctype>
#include <algorithm>
#include <array>
#include <atomic>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <immintrin.h>
#include <iomanip>
#include <limits>
#include <exception>
#include <functional>
#include <memory>
#include <random>
#include <stdexcept>
#include <string>
#include <thread>
#include <unordered_map>
#include <unordered_set>
#include <vector>
#include "candidate_rng.hpp"
#include "gost_reduced_model.hpp"
#include "grover_analytic.hpp"
#include "search_runtime.hpp"
#include "quantum_collision_search.hpp"
#include "herding_search.hpp"

using herding_link::LinkResult;
using herding_link::QuantumLinkResult;
using herding_link::QuantumTargets;
using herding_link::find_link64;
using herding_link::find_link_full;
using herding_link::find_link;
using herding_link::find_quantum_link;

using quantum_diamond::QuantumTableEntry;
using quantum_diamond::QuantumQram;
using quantum_diamond::QuantumEdge;
using quantum_diamond::QuantumLayerResult;
using quantum_diamond::QuantumLayerWorkspace;
using quantum_diamond::evaluate_message_space_into;
using quantum_diamond::build_quantum_layer;

using grover_analytic::optimal_grover_iterations;
using grover_analytic::grover_success_probability_analytic;
using grover_statevector::simulate_grover_statevector;

using gost_reduced_model::State;
using gost_reduced_model::LPS_TABLE;
using gost_reduced_model::byte_be;
using gost_reduced_model::LPS;
using gost_reduced_model::CompressionContext;
using gost_reduced_model::make_context;
using gost_reduced_model::compress_with_context;
using gost_reduced_model::compress_state;
using gost_reduced_model::hex_value;
using gost_reduced_model::reduced_state_from_hex;
using gost_reduced_model::reduced_state_to_hex;
using gost_reduced_model::random_state;
using gost_reduced_model::sigma_mask64;
using gost_reduced_model::required_sigma_low64;
using gost_reduced_model::set_low_sigma_bits;
using gost_reduced_model::random_state_constrained;

// Преобразует состояния только на границе командного интерфейса.
static State state_from_hex(const std::string& s) {
    if (s.size() != 128) throw std::runtime_error("expected 128 hex chars");
    State out{};
    for (size_t word = 0; word < 8; ++word) {
        uint64_t v = 0;
        for (size_t j = 0; j < 16; ++j) v = (v << 4) | static_cast<uint64_t>(hex_value(s[word * 16 + j]));
        out[word] = v;
    }
    return out;
}

static std::string state_to_hex(const State& s) {
    static constexpr char HEX[] = "0123456789abcdef";
    std::string out(128, '0');
    for (size_t word = 0; word < 8; ++word) {
        uint64_t v = s[word];
        for (int nibble = 15; nibble >= 0; --nibble) {
            out[word * 16 + static_cast<size_t>(nibble)] = HEX[v & 0xfu];
            v >>= 4;
        }
    }
    return out;
}

struct CollisionResult {
    State m1{}, m2{};
    State state{};
    uint64_t queries = 0;
    bool ok = false;
};

static uint64_t default_table_size(int n) {
    return std::max<uint64_t>(16, std::min<uint64_t>(1ULL << std::min(18, (n + 1) / 2), 1ULL << 18));
}

using FlatCollisionTable64=FlatTable64<State>;

static inline uint64_t hash_reduced_key(const ReducedKey& key) noexcept {
    uint64_t h = 0x9e3779b97f4a7c15ULL;
    for (uint64_t x : key.w) {
        h ^= mix64(x) + 0x9e3779b97f4a7c15ULL + (h << 6) + (h >> 2);
    }
    return mix64(h);
}

class FlatCollisionTableFull {
public:
    explicit FlatCollisionTableFull(uint64_t expected)
        : slots_(table_capacity_for(expected)), mask_(slots_.size() - 1) {}

    void begin_epoch() {
        ++generation_;
        if (generation_ == 0) {
            for (auto& slot : slots_) slot.generation = 0;
            generation_ = 1;
        }
    }

    void insert(const ReducedKey& key, const State& message) noexcept {
        size_t idx = static_cast<size_t>(hash_reduced_key(key)) & mask_;
        for (;;) {
            Entry& slot = slots_[idx];
            if (slot.generation != generation_) {
                slot.key = key;
                slot.message = message;
                slot.generation = generation_;
                return;
            }
            if (slot.key == key) return;
            idx = (idx + 1) & mask_;
        }
    }

    const State* find(const ReducedKey& key) const noexcept {
        size_t idx = static_cast<size_t>(hash_reduced_key(key)) & mask_;
        for (;;) {
            const Entry& slot = slots_[idx];
            if (slot.generation != generation_) return nullptr;
            if (slot.key == key) return &slot.message;
            idx = (idx + 1) & mask_;
        }
    }

private:
    struct Entry {
        ReducedKey key{};
        State message{};
        uint32_t generation = 0;
    };
    std::vector<Entry> slots_;
    size_t mask_ = 0;
    uint32_t generation_ = 0;
};

template<class Table, class Key>
static CollisionResult seeded_collision(const State& h1,const State& h2,uint64_t N,int n,int rounds,
    uint64_t limit,int threads,int s,uint64_t left_sigma,uint64_t right_sigma,uint64_t target_sigma,Key key) {
    const uint64_t table_size=default_table_size(n);
    Table table(table_size);
    const auto left=make_context(h1,N,rounds),right=make_context(h2,N,rounds);
    std::mt19937_64 rng(mix64(requested_seed));
    auto fast_rng=optional_candidate_rng();
    std::vector<State> messages,outputs;
    WorkerPool pool(threads,std::min<uint64_t>(4096,table_size),1024);
    uint64_t charged=0,physical=0;
    auto generate=[&](uint64_t batch_size,uint64_t low) {
        messages.resize(static_cast<size_t>(batch_size));
        fill_candidates(messages,rng,fast_rng.get(),low,s);
    };
    while(limit-charged>=2) {
        table.begin_epoch();
        const uint64_t left_goal=std::min(table_size,(limit-charged)/2);
        for(uint64_t i=0;i<left_goal;) {
            const uint64_t batch_size=std::min<uint64_t>(4096,left_goal-i);
            generate(batch_size,required_sigma_low64(left_sigma,target_sigma,s));
            hash_seeded_batch(left,messages,outputs,threads,&pool);
            physical+=batch_size;
            for(size_t j=0;j<outputs.size();++j)table.insert(key(outputs[j],n),messages[j]);
            i+=batch_size;charged+=batch_size;
        }
        const uint64_t right_goal=std::min(table_size,limit-charged);
        for(uint64_t i=0;i<right_goal;) {
            const uint64_t batch_size=std::min<uint64_t>(4096,right_goal-i);
            generate(batch_size,required_sigma_low64(right_sigma,target_sigma,s));
            hash_seeded_batch(right,messages,outputs,threads,&pool);
            physical+=batch_size;
            for(size_t j=0;j<outputs.size();++j)if(const State* partner=table.find(key(outputs[j],n))) {
                // Сохраняет исходный счётчик пакета из восьми кандидатов, учитывая последующие вычисления только как работу симулятора.

                const uint64_t logical=std::min<uint64_t>(batch_size,((j/SEARCH_BATCH)+1)*SEARCH_BATCH);
                if(std::getenv("NOSTRADAMUS_SEARCH_DEBUG"))std::cerr<<"physical_hash_evaluations="<<physical<<" logical_queries="<<charged+logical<<'\n';
                return {*partner,messages[j],outputs[j],charged+logical,true};
            }
            i+=batch_size;charged+=batch_size;
        }
    }
    throw std::runtime_error("collision not found within trials_limit");
}

static CollisionResult find_collision64(const State& h1, const State& h2, uint64_t N, int n, int rounds,
                                        uint64_t limit, int requested_threads, int sigma_bits = 0,
                                        uint64_t left_sigma = 0, uint64_t right_sigma = 0, uint64_t target_sigma = 0) {
    if(has_requested_seed && (nthreads_from(requested_threads)!=1 || requested_rng!="mt19937"))return seeded_collision<FlatCollisionTable64>(h1,h2,N,n,rounds,limit,requested_threads,sigma_bits,left_sigma,right_sigma,target_sigma,reduced_key64);
    const uint64_t left_required = required_sigma_low64(left_sigma, target_sigma, sigma_bits);
    const uint64_t right_required = required_sigma_low64(right_sigma, target_sigma, sigma_bits);
    const uint64_t table_size = default_table_size(n);
    const int nt = workers_for_limit(requested_threads, limit, 2);
    const CompressionContext ctx1 = make_context(h1, N, rounds);
    const CompressionContext ctx2 = make_context(h2, N, rounds);
    std::atomic<bool> found(false);
    std::vector<uint64_t> completed(static_cast<size_t>(nt), 0);
    CollisionResult result;

    auto worker = [&](int tid) {
        const WorkRange range = work_range_for(limit, nt, tid);
        const uint64_t quota = range.end - range.begin;
        uint64_t local_queries = 0;
        std::seed_seq seq{uint32_t(std::random_device{}()),
                          uint32_t(std::chrono::high_resolution_clock::now().time_since_epoch().count()),
                          uint32_t(tid), uint32_t(range.begin), uint32_t(range.begin >> 32)};
        std::mt19937_64 rng(seq);
        if (has_requested_seed) rng.seed(mix64(requested_seed ^ uint64_t(tid) ^ range.begin));
        FlatCollisionTable64 table(table_size);
        SearchBatch messages{};
        SearchBatch outputs{};

        while (quota - local_queries >= 2 && !found.load(std::memory_order_relaxed)) {
            table.begin_epoch();
            const uint64_t remaining = quota - local_queries;
            const uint64_t left_goal = std::min<uint64_t>(table_size, remaining / 2);
            uint64_t i = 0;
            while (i < left_goal && !found.load(std::memory_order_relaxed)) {
                const size_t count = static_cast<size_t>(
                    std::min<uint64_t>(SEARCH_BATCH, left_goal - i));
                for (size_t lane = 0; lane < count; ++lane) messages[lane] = random_state_constrained(rng, left_required, sigma_bits);
                compress_batch(messages, outputs, count, ctx1);
                local_queries += count;
                for (size_t lane = 0; lane < count; ++lane) {
                    table.insert(reduced_key64(outputs[lane], n), messages[lane]);
                }
                i += count;
            }

            const uint64_t right_goal = std::min<uint64_t>(table_size, quota - local_queries);
            i = 0;
            while (i < right_goal && !found.load(std::memory_order_relaxed)) {
                const size_t count = static_cast<size_t>(
                    std::min<uint64_t>(SEARCH_BATCH, right_goal - i));
                for (size_t lane = 0; lane < count; ++lane) messages[lane] = random_state_constrained(rng, right_required, sigma_bits);
                compress_batch(messages, outputs, count, ctx2);
                local_queries += count;
                for (size_t lane = 0; lane < count; ++lane) {
                    const uint64_t key = reduced_key64(outputs[lane], n);
                    if (const State* m1 = table.find(key)) {
                        bool expected = false;
                        if (found.compare_exchange_strong(expected, true,
                                                          std::memory_order_relaxed)) {
                            result.m1 = *m1;
                            result.m2 = messages[lane];
                            result.state = outputs[lane];
                            result.ok = true;
                        }
                        break;
                    }
                }
                i += count;
            }
        }
        completed[static_cast<size_t>(tid)] = local_queries;
    };

    std::vector<std::thread> threads;
    threads.reserve(static_cast<size_t>(nt));
    for (int i = 0; i < nt; ++i) threads.emplace_back(worker, i);
    for (auto& x : threads) x.join();
    if (result.ok) { result.queries = sum_completed(completed); return result; }
    throw std::runtime_error("collision not found within trials_limit");
}

static CollisionResult find_collision_full(const State& h1, const State& h2, uint64_t N, int n, int rounds,
                                            uint64_t limit, int requested_threads, int sigma_bits = 0,
                                            uint64_t left_sigma = 0, uint64_t right_sigma = 0, uint64_t target_sigma = 0) {
    if(has_requested_seed && (nthreads_from(requested_threads)!=1 || requested_rng!="mt19937"))return seeded_collision<FlatCollisionTableFull>(h1,h2,N,n,rounds,limit,requested_threads,sigma_bits,left_sigma,right_sigma,target_sigma,reduced_key_full);
    const uint64_t left_required = required_sigma_low64(left_sigma, target_sigma, sigma_bits);
    const uint64_t right_required = required_sigma_low64(right_sigma, target_sigma, sigma_bits);
    const uint64_t table_size = default_table_size(n);
    const int nt = workers_for_limit(requested_threads, limit, 2);
    const CompressionContext ctx1 = make_context(h1, N, rounds);
    const CompressionContext ctx2 = make_context(h2, N, rounds);
    std::atomic<bool> found(false);
    std::vector<uint64_t> completed(static_cast<size_t>(nt), 0);
    CollisionResult result;

    auto worker = [&](int tid) {
        const WorkRange range = work_range_for(limit, nt, tid);
        const uint64_t quota = range.end - range.begin;
        uint64_t local_queries = 0;
        std::seed_seq seq{uint32_t(std::random_device{}()),
                          uint32_t(std::chrono::high_resolution_clock::now().time_since_epoch().count()),
                          uint32_t(tid), uint32_t(range.begin), uint32_t(range.begin >> 32)};
        std::mt19937_64 rng(seq);
        if (has_requested_seed) rng.seed(mix64(requested_seed ^ uint64_t(tid) ^ range.begin));
        FlatCollisionTableFull table(table_size);
        SearchBatch messages{};
        SearchBatch outputs{};

        while (quota - local_queries >= 2 && !found.load(std::memory_order_relaxed)) {
            table.begin_epoch();
            const uint64_t remaining = quota - local_queries;
            const uint64_t left_goal = std::min<uint64_t>(table_size, remaining / 2);
            uint64_t i = 0;
            while (i < left_goal && !found.load(std::memory_order_relaxed)) {
                const size_t count = static_cast<size_t>(
                    std::min<uint64_t>(SEARCH_BATCH, left_goal - i));
                for (size_t lane = 0; lane < count; ++lane) messages[lane] = random_state_constrained(rng, left_required, sigma_bits);
                compress_batch(messages, outputs, count, ctx1);
                local_queries += count;
                for (size_t lane = 0; lane < count; ++lane) {
                    table.insert(reduced_key_full(outputs[lane], n), messages[lane]);
                }
                i += count;
            }

            const uint64_t right_goal = std::min<uint64_t>(table_size, quota - local_queries);
            i = 0;
            while (i < right_goal && !found.load(std::memory_order_relaxed)) {
                const size_t count = static_cast<size_t>(
                    std::min<uint64_t>(SEARCH_BATCH, right_goal - i));
                for (size_t lane = 0; lane < count; ++lane) messages[lane] = random_state_constrained(rng, right_required, sigma_bits);
                compress_batch(messages, outputs, count, ctx2);
                local_queries += count;
                for (size_t lane = 0; lane < count; ++lane) {
                    const ReducedKey key = reduced_key_full(outputs[lane], n);
                    if (const State* m1 = table.find(key)) {
                        bool expected = false;
                        if (found.compare_exchange_strong(expected, true,
                                                          std::memory_order_relaxed)) {
                            result.m1 = *m1;
                            result.m2 = messages[lane];
                            result.state = outputs[lane];
                            result.ok = true;
                        }
                        break;
                    }
                }
                i += count;
            }
        }
        completed[static_cast<size_t>(tid)] = local_queries;
    };

    std::vector<std::thread> threads;
    threads.reserve(static_cast<size_t>(nt));
    for (int i = 0; i < nt; ++i) threads.emplace_back(worker, i);
    for (auto& x : threads) x.join();
    if (result.ok) { result.queries = sum_completed(completed); return result; }
    throw std::runtime_error("collision not found within trials_limit");
}

static CollisionResult find_collision(const std::string& h1_hex, const std::string& h2_hex, uint64_t N, int n,
                                      int rounds, uint64_t limit, int requested_threads, int sigma_bits = 0,
                                      uint64_t left_sigma = 0, uint64_t right_sigma = 0, uint64_t target_sigma = 0) {
    const State h1 = reduced_state_from_hex(h1_hex, n);
    const State h2 = reduced_state_from_hex(h2_hex, n);
    return n <= 64 ? find_collision64(h1, h2, N, n, rounds, limit, requested_threads, sigma_bits, left_sigma, right_sigma, target_sigma)
                   : find_collision_full(h1, h2, N, n, rounds, limit, requested_threads, sigma_bits, left_sigma, right_sigma, target_sigma);
}

struct TransitionSample {
    State block{};
    State output{};
};

static std::vector<State> evaluate_message_space(const CompressionContext& ctx,
    const std::vector<State>& messages,int requested_threads) {
    std::vector<State> outputs;
    evaluate_message_space_into(ctx,messages,outputs,requested_threads);
    return outputs;
}

// Вычисляет переходы Blackburn пакетами AVX2 с контекстом каждой вершины и непересекающимися диапазонами потоков.

static std::vector<TransitionSample> sample_transition_lists(
    const std::vector<std::string>& state_hex,
    uint64_t samples_per_state,
    uint64_t N,
    int n,
    int rounds,
    int requested_threads,
    int sigma_bits = 0,
    uint64_t current_sigma = 0,
    uint64_t target_sigma = 0,
    WorkerPool* external_pool = nullptr
) {
    const uint64_t required_low = required_sigma_low64(current_sigma, target_sigma, sigma_bits);
    if (state_hex.empty()) throw std::runtime_error("state list is empty");
    if (samples_per_state == 0) throw std::runtime_error("samples_per_state must be positive");
    if (samples_per_state > std::numeric_limits<uint64_t>::max() / state_hex.size()) {
        throw std::runtime_error("sample count overflow");
    }
    const uint64_t total = samples_per_state * static_cast<uint64_t>(state_hex.size());
    if (total > static_cast<uint64_t>(std::numeric_limits<size_t>::max())) {
        throw std::runtime_error("sample result is too large");
    }

    std::vector<CompressionContext> contexts;
    contexts.reserve(state_hex.size());
    for (const auto& state : state_hex) {
        contexts.push_back(make_context(reduced_state_from_hex(state, n), N, rounds));
    }

    std::vector<TransitionSample> result(static_cast<size_t>(total));
    const int nt = workers_for_limit(requested_threads, total, 1);

    if(has_requested_seed && (nthreads_from(requested_threads)!=1 || requested_rng!="mt19937")) {
        std::mt19937_64 rng(mix64(requested_seed));
        auto fast_rng=optional_candidate_rng();
        // Сохраняет исходный порядок кандидатов по вершинам для одного потока.
        if(fast_rng)for(auto& item:result)item.block=random_state_constrained(*fast_rng,required_low,sigma_bits);
        else for(auto& item:result)item.block=random_state_constrained(rng,required_low,sigma_bits);
        auto work=[&](WorkRange range) {
            SearchBatch messages{},outputs{};
            for(uint64_t index=range.begin;index<range.end;) {
                const uint64_t vertex=index/samples_per_state,offset=index%samples_per_state;
                const size_t batch_size=static_cast<size_t>(std::min<uint64_t>(SEARCH_BATCH,std::min(range.end-index,samples_per_state-offset)));
                for(size_t lane=0;lane<batch_size;++lane)messages[lane]=result[static_cast<size_t>(index+lane)].block;
                compress_batch(messages,outputs,batch_size,contexts[static_cast<size_t>(vertex)]);
                for(size_t lane=0;lane<batch_size;++lane)result[static_cast<size_t>(index+lane)].output=outputs[lane];
                index+=batch_size;
            }
        };
        if(external_pool)external_pool->run(total,1024,work);
        else parallel_ranges(total,requested_threads,1024,work);
        return result;
    }

    auto worker = [&](int tid) {
        const WorkRange range = work_range_for(total, nt, tid);
        std::seed_seq seq{uint32_t(std::random_device{}()),
                          uint32_t(std::chrono::high_resolution_clock::now().time_since_epoch().count()),
                          uint32_t(tid), uint32_t(range.begin), uint32_t(range.begin >> 32)};
        std::mt19937_64 rng(seq);
        if (has_requested_seed) rng.seed(mix64(requested_seed ^ uint64_t(tid) ^ range.begin));
        SearchBatch messages{};
        SearchBatch outputs{};

        uint64_t index = range.begin;
        while (index < range.end) {
            const uint64_t vertex = index / samples_per_state;
            const uint64_t offset = index % samples_per_state;
            const size_t count = static_cast<size_t>(std::min<uint64_t>(
                SEARCH_BATCH,
                std::min<uint64_t>(range.end - index, samples_per_state - offset)));
            for (size_t lane = 0; lane < count; ++lane) messages[lane] = random_state_constrained(rng, required_low, sigma_bits);
            compress_batch(messages, outputs, count, contexts[static_cast<size_t>(vertex)]);
            for (size_t lane = 0; lane < count; ++lane) {
                result[static_cast<size_t>(index + lane)] = {messages[lane], outputs[lane]};
            }
            index += count;
        }
    };

    if(nt==1)worker(0);
    else {
        std::vector<std::thread> threads;
        threads.reserve(static_cast<size_t>(nt));
        for (int tid = 0; tid < nt; ++tid) threads.emplace_back(worker, tid);
        for (auto& thread : threads) thread.join();
    }
    return result;
}

static void selftest_batch_kernel() {
    std::mt19937_64 rng(0x53545249424f4755ULL);
    for (int rounds : {1, 2, 6, 12}) {
        for (uint64_t N : {0ULL, 512ULL, 1024ULL, 3584ULL}) {
            State h{};
            for (auto& x : h) x = rng();
            const CompressionContext ctx = make_context(h, N, rounds);
            SearchBatch messages{};
            SearchBatch batch_out{};
            for (auto& m : messages) m = random_state(rng);
            compress_batch(messages, batch_out, SEARCH_BATCH, ctx);
            for (size_t i = 0; i < SEARCH_BATCH; ++i) {
                const State scalar = compress_with_context(messages[i], ctx);
                if (scalar != batch_out[i]) {
                    throw std::runtime_error("AVX2 batch kernel mismatch");
                }
            }
        }
    }
}

static void selftest_quantum_kernel() {
    std::mt19937_64 rng(0x47524f564552ULL);
    uint64_t queries = 0;
    double probability = 0.0;
    double norm_error = 0.0;
    std::vector<uint8_t> one_marked(8, 0);
    one_marked[3] = 1;
    const auto one = simulate_grover_statevector(one_marked, 2, rng);
    queries = one.iterations; probability = one.success_probability; norm_error = one.norm_error;
    if (queries != 2 || std::abs(probability - 0.9453125) > 1e-12 ||
        norm_error > 1e-12) {
        throw std::runtime_error("Grover single-solution selftest mismatch");
    }
    const double analytic_probability = grover_success_probability_analytic(8, 1, 2);
    if (std::abs(analytic_probability - probability) > 1e-12) {
        throw std::runtime_error("Grover analytic/state-vector probability mismatch");
    }

    queries = 0;
    std::vector<uint8_t> four_marked(16, 0);
    for (size_t i : {size_t{0}, size_t{4}, size_t{8}, size_t{12}}) {
        four_marked[i] = 1;
    }
    const auto four = simulate_grover_statevector(four_marked, 1, rng);
    queries = four.iterations; probability = four.success_probability; norm_error = four.norm_error;
    if (queries != 1 || std::abs(probability - 1.0) > 1e-12 ||
        norm_error > 1e-12) {
        throw std::runtime_error("Grover multi-solution selftest mismatch");
    }
}

static uint64_t u64(const char* s) { return std::stoull(s); }
static int i32(const char* s) { return std::stoi(s); }

static std::vector<std::string> read_stdin_tokens(int count, const char* label) {
    if (count < 0) throw std::runtime_error(std::string(label) + " count is negative");
    std::vector<std::string> values;
    values.reserve(static_cast<size_t>(count));
    for (int i = 0; i < count; ++i) {
        std::string value;
        if (!(std::cin >> value)) {
            throw std::runtime_error(std::string(label) + " stdin payload is incomplete");
        }
        values.push_back(std::move(value));
    }
    std::string extra;
    if (std::cin >> extra) {
        throw std::runtime_error(std::string(label) + " stdin payload has extra values");
    }
    return values;
}

static State add512(const State& a, const State& b) {
    State out{};
    uint64_t carry = 0;
    for (int i = 7; i >= 0; --i) {
        const uint64_t sum = a[i] + b[i];
        const bool c1 = sum < a[i];
        out[i] = sum + carry;
        const bool c2 = out[i] < sum;
        carry = c1 || c2;
    }
    return out;
}

// Обрабатывает правые полные блоки по RFC 6986 и всегда сжимает дополненный остаток.

static std::string full_hash(std::string message, int bits) {
    if (bits != 256 && bits != 512) throw std::runtime_error("hash bits must be 256 or 512");
    for (char c : message) if (!std::isxdigit(static_cast<unsigned char>(c)))
        throw std::runtime_error("hash message must be hexadecimal");
    State h{};
    if (bits == 256) h.fill(0x0101010101010101ULL);
    State n{}, sigma{}, increment{};
    increment[7] = 512;
    while (message.size() >= 128) {
        const State block = state_from_hex(message.substr(message.size() - 128));
        h = compress_with_context(block, make_context(h, n, 12));
        n = add512(n, increment);
        sigma = add512(sigma, block);
        message.resize(message.size() - 128);
    }
    increment[7] = message.size() * 4;
    const State last = state_from_hex(std::string(127 - message.size(), '0') + "1" + message);
    h = compress_with_context(last, make_context(h, n, 12));
    n = add512(n, increment);
    sigma = add512(sigma, last);
    h = compress_with_context(n, make_context(h, uint64_t{0}, 12));
    h = compress_with_context(sigma, make_context(h, uint64_t{0}, 12));
    const auto hex = state_to_hex(h);
    return bits == 256 ? hex.substr(0, 64) : hex;
}

#include "blackburn_layer.hpp"

int main(int argc, char** argv) {
    try {
        if(const char* value=std::getenv("NOSTRADAMUS_QRAM_IMPL"))requested_qram=value;
        if(const char* value=std::getenv("NOSTRADAMUS_RNG"))requested_rng=value;
        while(argc>=4) {
            const std::string option=argv[argc-2];
            if(option=="--rng")requested_rng=argv[argc-1];
            else if(option=="--qram-impl")requested_qram=argv[argc-1];
            else if(option=="--seed"){has_requested_seed=true;requested_seed=u64(argv[argc-1]);}
            else break;
            argc-=2;
        }
        if(requested_rng!="mt19937" && requested_rng!="xoshiro256ss")throw std::runtime_error("rng must be mt19937 or xoshiro256ss");
        if(requested_qram!="auto" && requested_qram!="generic" && requested_qram!="u64")throw std::runtime_error("qram implementation must be auto, generic or u64");
        if (argc < 2) throw std::runtime_error("missing command");
        const std::string cmd = argv[1];
        if(requested_rng=="xoshiro256ss" && !has_requested_seed) {
            // Координатор формирует кандидаты из одного начального значения генератора для всех потоков.

            requested_seed=(uint64_t(std::random_device{}())<<32)^std::random_device{}();
            has_requested_seed=true;
        }
        if(cmd=="blackburn-layer") {
            if(argc!=10)throw std::runtime_error("blackburn-layer count N n rounds threads s current_sigma target_sigma");
            const int count=i32(argv[2]);
            if(count<2)throw std::runtime_error("invalid Blackburn state count");
            std::vector<std::string> states(static_cast<size_t>(count));
            for(auto& state:states)if(!(std::cin>>state))throw std::runtime_error("incomplete Blackburn states");
            run_blackburn_layer(states,u64(argv[3]),i32(argv[4]),i32(argv[5]),i32(argv[6]),i32(argv[7]),u64(argv[8]),u64(argv[9]));
        } else if (cmd == "hash") {
            if (argc != 4) throw std::runtime_error("usage: hash message_hex bits");
            std::cout << "OK " << full_hash(argv[2], i32(argv[3])) << "\n";
        } else if (cmd == "lps") {
            if (argc != 3) throw std::runtime_error("usage: lps vector_hex");
            std::cout << "OK " << state_to_hex(LPS(state_from_hex(argv[2]))) << "\n";
        } else if (cmd == "compress-wide") {
            if (argc != 6) throw std::runtime_error("usage: compress-wide m h N_hex rounds");
            const auto ctx = make_context(state_from_hex(argv[3]), state_from_hex(argv[4]), i32(argv[5]));
            std::cout << "OK " << state_to_hex(compress_with_context(state_from_hex(argv[2]), ctx)) << "\n";
        } else if (cmd == "compress") {
            if (argc != 6) throw std::runtime_error("usage: compress m h N rounds");
            const State out = compress_state(state_from_hex(argv[2]), state_from_hex(argv[3]), u64(argv[4]), i32(argv[5]));
            std::cout << "OK " << state_to_hex(out) << "\n";
        } else if (cmd == "reduced") {
            if (argc != 7) throw std::runtime_error("usage: reduced m state N rounds n");
            const int n = i32(argv[6]);
            const State out = compress_state(state_from_hex(argv[2]), reduced_state_from_hex(argv[3], n), u64(argv[4]), i32(argv[5]));
            std::cout << "OK " << reduced_state_to_hex(out, n) << "\n";
        } else if (cmd == "collision" || cmd == "collision-sigma") {
            const bool sigma_mode = cmd == "collision-sigma";
            if ((!sigma_mode && argc != 9) || (sigma_mode && argc != 13))
                throw std::runtime_error("usage: collision[-sigma] h1 h2 N n rounds limit threads [s left_sigma right_sigma target_sigma]");
            const int n = i32(argv[5]);
            auto r = find_collision(argv[2], argv[3], u64(argv[4]), n, i32(argv[6]), u64(argv[7]), i32(argv[8]),
                                    sigma_mode ? i32(argv[9]) : 0, sigma_mode ? u64(argv[10]) : 0,
                                    sigma_mode ? u64(argv[11]) : 0, sigma_mode ? u64(argv[12]) : 0);
            std::cout << "OK " << state_to_hex(r.m1) << ' ' << state_to_hex(r.m2) << ' '
                      << reduced_state_to_hex(r.state, n) << ' ' << r.queries << "\n";
        } else if (cmd == "link" || cmd == "link-stdin" || cmd == "link-sigma-stdin") {
            const bool sigma_mode = cmd == "link-sigma-stdin";
            const bool from_stdin = cmd == "link-stdin" || sigma_mode;
            if ((!from_stdin && argc < 10) || (!sigma_mode && from_stdin && argc != 9) || (sigma_mode && argc != 12)) {
                throw std::runtime_error("usage: link[-stdin] ... or link-sigma-stdin prefix N n rounds limit threads count s current_sigma target_sigma");
            }
            const int n = i32(argv[4]);
            const int count = i32(argv[8]);
            if (count < 1 || (!from_stdin && argc != 9 + count)) throw std::runtime_error("target count mismatch");
            std::vector<std::string> targets = from_stdin ? read_stdin_tokens(count, "link targets") : std::vector<std::string>(argv + 9, argv + 9 + count);
            auto r = find_link(argv[2], u64(argv[3]), n, i32(argv[5]), u64(argv[6]), i32(argv[7]), targets,
                               sigma_mode ? i32(argv[9]) : 0, sigma_mode ? u64(argv[10]) : 0, sigma_mode ? u64(argv[11]) : 0);
            std::cout << "OK " << state_to_hex(r.block) << ' ' << reduced_state_to_hex(r.state, n) << ' ' << r.queries << "\n";
        } else if (cmd == "sample" || cmd == "sample-stdin" || cmd == "sample-sigma-stdin") {
            const bool sigma_mode = cmd == "sample-sigma-stdin";
            const bool from_stdin = cmd == "sample-stdin" || sigma_mode;
            if ((!from_stdin && argc < 9) || (!sigma_mode && from_stdin && argc != 8) || (sigma_mode && argc != 11))
                throw std::runtime_error("usage: sample[-stdin] ... or sample-sigma-stdin state_count samples N n rounds threads s current_sigma target_sigma");
            const int state_count = i32(argv[2]);
            if (state_count < 1 || (!from_stdin && argc != 8 + state_count)) throw std::runtime_error("sample state count mismatch");
            const uint64_t samples_per_state = u64(argv[3]);
            const int n = i32(argv[5]);
            std::vector<std::string> states = from_stdin ? read_stdin_tokens(state_count, "sample states") : std::vector<std::string>(argv + 8, argv + 8 + state_count);
            const auto samples = sample_transition_lists(states, samples_per_state, u64(argv[4]), n, i32(argv[6]), i32(argv[7]),
                sigma_mode ? i32(argv[8]) : 0, sigma_mode ? u64(argv[9]) : 0, sigma_mode ? u64(argv[10]) : 0);
            std::cout << "OK";
            for (const auto& sample : samples) {
                std::cout << ' ' << state_to_hex(sample.block)
                          << ' ' << reduced_state_to_hex(sample.output, n);
            }
            std::cout << "\n";
        } else if (cmd == "bbht-layer-stdin" || cmd == "bbht-link-stdin") {
            const bool layer = cmd == "bbht-layer-stdin";
            if (argc != (layer ? 19 : 18))
                throw std::runtime_error("Неверное число аргументов команды BBHT.");
            const int base = layer ? 14 : 13;
            bbht_adaptive::Options options;
            options.growth = std::stod(argv[base]);
            options.max_attempts = u64(argv[base + 1]);
            options.max_oracle_queries = u64(argv[base + 2]);
            options.dense_max_states = u64(argv[base + 3]);
            options.max_stage_seconds = std::stod(argv[base + 4]);
            const int n = i32(argv[layer ? 7 : 6]);
            const int s = i32(argv[layer ? 11 : 10]);
            const uint64_t N = u64(argv[layer ? 6 : 5]);
            const int rounds = i32(argv[layer ? 8 : 7]);
            if (n < 4 || n > 512 || n % 4 || s < 0 || s > 64 || N % 512 ||
                rounds < 1 || rounds > 12 || !std::isfinite(options.growth) ||
                options.growth <= 1 || options.growth > 4 || !options.max_attempts ||
                !options.max_oracle_queries || !options.dense_max_states ||
                !std::isfinite(options.max_stage_seconds) || options.max_stage_seconds < 0)
                throw std::runtime_error("Недопустимые параметры BBHT.");
            if (layer) {
                const auto states = read_stdin_tokens(i32(argv[2]), "Состояния уровня BBHT");
                const auto result = quantum_diamond_bbht::build_layer(states, u64(argv[3]),
                    u64(argv[4]), i32(argv[5]), N, n, rounds, u64(argv[9]), i32(argv[10]),
                    s, u64(argv[12]), u64(argv[13]), options);
                const auto& value = result.layer;
                std::cout << "OK " << value.oracle_queries << ' ' << value.simulator_evaluations
                          << ' ' << value.qram_entries << ' ' << value.grover_successes << ' ' << value.edges.size();
                for (const auto& edge : value.edges)
                    std::cout << ' ' << edge.left << ' ' << edge.right << ' ' << state_to_hex(edge.left_block)
                              << ' ' << state_to_hex(edge.right_block) << ' ' << reduced_state_to_hex(edge.common, n);
                std::cout << " SV " << value.statevector_elements_processed << ' ' << value.statevector_iterations
                          << ' ' << value.grover_attempts << ' ' << value.marked_elements << ' ' << value.verification_evaluations
                          << ' ' << std::setprecision(17) << value.success_probability_sum
                          << ' ' << value.statevector_norm_error_max << ' ' << value.statevector_seconds;
                std::cout << " BBHT " << result.phase_oracle_queries << ' ' << result.verification_queries
                          << ' ' << result.failures << ' ' << value.grover_attempts << ' '
                          << (u64(argv[4]) <= options.dense_max_states ? "dense" : "symmetric");
                bbht_adaptive::write_diagnostics(std::cout, value.search_diagnostics);
                std::cout << '\n';
            } else {
                const auto targets = read_stdin_tokens(i32(argv[3]), "Листья BBHT");
                const auto result = herding_link_bbht::find(argv[2], targets, u64(argv[4]), N,
                    n, rounds, u64(argv[8]), i32(argv[9]), s, u64(argv[11]), u64(argv[12]), options);
                const auto& value = result.link;
                std::cout << "OK " << (value.found ? 1 : 0) << ' ' << value.oracle_queries << ' '
                          << value.simulator_evaluations << ' ' << value.marked_count << ' '
                          << std::setprecision(17) << value.success_probability << ' ' << value.norm_error;
                if (value.found) std::cout << ' ' << state_to_hex(value.block) << ' ' << reduced_state_to_hex(value.target, n);
                std::cout << " SV " << value.statevector_elements_processed << ' ' << value.statevector_iterations
                          << ' ' << value.verification_evaluations << ' ' << value.statevector_seconds;
                std::cout << " BBHT " << result.search.phase_oracle_queries << ' ' << result.search.verification_queries
                          << ' ' << result.search.failures << ' ' << result.search.attempts << ' '
                          << (u64(argv[4]) <= options.dense_max_states ? "dense" : "symmetric");
                bbht_adaptive::write_diagnostics(std::cout, value.search_diagnostics);
                std::cout << '\n';
            }
        } else if (cmd == "quantum-layer" || cmd == "quantum-layer-stdin" || cmd == "quantum-layer-sigma-stdin") {
            const bool sigma_mode = cmd == "quantum-layer-sigma-stdin";
            const bool from_stdin = cmd == "quantum-layer-stdin" || sigma_mode;
            if ((!from_stdin && argc < 13) || (!sigma_mode && from_stdin && argc != 11) || (sigma_mode && argc != 14))
                throw std::runtime_error("usage: quantum-layer[-stdin] ... or quantum-layer-sigma-stdin ... s current_sigma target_sigma");
            const int state_count = i32(argv[2]);
            if (state_count < 2 || (!from_stdin && argc != 11 + state_count)) throw std::runtime_error("quantum-layer state count mismatch");
            const int n = i32(argv[7]);
            std::vector<std::string> states = from_stdin ? read_stdin_tokens(state_count, "quantum-layer states") : std::vector<std::string>(argv + 11, argv + 11 + state_count);
            const auto result = build_quantum_layer(states, u64(argv[3]), u64(argv[4]), i32(argv[5]), u64(argv[6]), n, i32(argv[8]), u64(argv[9]), i32(argv[10]),
                sigma_mode ? i32(argv[11]) : 0, sigma_mode ? u64(argv[12]) : 0, sigma_mode ? u64(argv[13]) : 0);
            std::cout << "OK " << result.oracle_queries << ' '
                      << result.simulator_evaluations << ' '
                      << result.qram_entries << ' '
                      << result.grover_successes << ' '
                      << result.edges.size();
            for (const auto& edge : result.edges) {
                std::cout << ' ' << edge.left << ' ' << edge.right
                          << ' ' << state_to_hex(edge.left_block)
                          << ' ' << state_to_hex(edge.right_block)
                          << ' ' << reduced_state_to_hex(edge.common, n);
            }
            std::cout << " SV " << result.statevector_elements_processed << ' '
                      << result.statevector_iterations << ' ' << result.grover_attempts << ' '
                      << result.marked_elements << ' ' << result.verification_evaluations << ' '
                      << std::setprecision(17) << result.success_probability_sum << ' '
                      << result.statevector_norm_error_max << ' ' << result.statevector_seconds
                      << " AMP " << (u64(argv[4]) <= grover_oracle::dense_max_states ? "dense" : "symmetric");
            bbht_adaptive::write_diagnostics(std::cout, result.search_diagnostics);
            std::cout << '\n';
        } else if (cmd == "quantum-link" || cmd == "quantum-link-stdin" || cmd == "quantum-link-sigma-stdin") {
            const bool sigma_mode = cmd == "quantum-link-sigma-stdin";
            const bool from_stdin = cmd == "quantum-link-stdin" || sigma_mode;
            if ((!from_stdin && argc < 11) || (!sigma_mode && from_stdin && argc != 10) || (sigma_mode && argc != 13))
                throw std::runtime_error("usage: quantum-link[-stdin] ... or quantum-link-sigma-stdin ... s current_sigma target_sigma");
            const int target_count = i32(argv[3]);
            if (target_count < 1 || (!from_stdin && argc != 10 + target_count)) throw std::runtime_error("quantum-link target count mismatch");
            const int n = i32(argv[6]);
            std::vector<std::string> targets = from_stdin ? read_stdin_tokens(target_count, "quantum-link targets") : std::vector<std::string>(argv + 10, argv + 10 + target_count);
            const auto result = find_quantum_link(argv[2], targets, u64(argv[4]), u64(argv[5]), n, i32(argv[7]), u64(argv[8]), i32(argv[9]),
                sigma_mode ? i32(argv[10]) : 0, sigma_mode ? u64(argv[11]) : 0, sigma_mode ? u64(argv[12]) : 0);
            std::cout << "OK " << (result.found ? 1 : 0) << ' '
                      << result.oracle_queries << ' '
                      << result.simulator_evaluations << ' '
                      << result.marked_count << ' '
                      << std::setprecision(17) << result.success_probability << ' '
                      << result.norm_error;
            if (result.found) {
                std::cout << ' ' << state_to_hex(result.block)
                          << ' ' << reduced_state_to_hex(result.target, n);
            }
            std::cout << " SV " << result.statevector_elements_processed << ' '
                      << result.statevector_iterations << ' ' << result.verification_evaluations << ' '
                      << result.statevector_seconds
                      << " AMP " << (u64(argv[4]) <= grover_oracle::dense_max_states ? "dense" : "symmetric");
            bbht_adaptive::write_diagnostics(std::cout, result.search_diagnostics);
            std::cout << '\n';
        } else if (cmd == "grover-statevector-stdin" || cmd == "grover-study-stdin") {
            const bool study = cmd == "grover-study-stdin";
            if (argc != (study ? 6 : 5)) throw std::runtime_error("usage: grover-statevector-stdin S iterations seed [trials]");
            const uint64_t states = u64(argv[2]), iterations = u64(argv[3]), seed = u64(argv[4]);
            grover_statevector::check_resources(states, iterations, states <= 1048576 ? states * 8 : 0);
            std::vector<uint8_t> marked(static_cast<size_t>(states));
            for (auto& flag : marked) { int value; if (!(std::cin >> value) || value < 0 || value > 1) throw std::runtime_error("invalid marked flag"); flag = static_cast<uint8_t>(value); }
            const uint64_t trials = study ? u64(argv[5]) : 1;
            if (!trials || trials > 10000) throw std::runtime_error("invalid measurement count");
            grover_statevector::Deadline deadline;
            uint64_t successes = 0;
            uint64_t total_elements = 0;
            double total_seconds = 0, max_norm_error = 0;
            grover_statevector::Result result;
            std::vector<double> amplitudes;
            for (uint64_t trial = 0; trial < trials; ++trial) {
                deadline.check();
                std::mt19937_64 rng(seed + trial);
                result = simulate_grover_statevector(marked, iterations, rng, study ? nullptr : &amplitudes);
                successes += result.is_marked;
                total_elements += result.statevector_elements_processed;
                total_seconds += result.statevector_seconds;
                max_norm_error = std::max(max_norm_error, result.norm_error);
            }
            if (study) {
                result.statevector_elements_processed = total_elements;
                result.statevector_seconds = total_seconds;
                result.norm_error = max_norm_error;
            }
            std::cout << "OK " << result.measured_index << ' ' << result.is_marked << ' ' << result.marked_count << ' '
                      << result.iterations << ' ' << result.oracle_queries << ' ' << std::setprecision(17)
                      << result.success_probability << ' ' << result.norm_error << ' '
                      << result.statevector_elements_processed << ' ' << result.statevector_seconds << ' ' << successes;
            for (double value : amplitudes) std::cout << ' ' << value;
            std::cout << "\n";
        } else if (cmd == "version") {
            std::cout << "OK gost_core_v13_statevector_v2\n";
        } else if (cmd == "selftest-batch") {
            selftest_batch_kernel();
            selftest_quantum_kernel();
            std::cout << "OK AVX2_AND_GROVER_SELFTEST_PASS\n";
        } else {
            throw std::runtime_error("unknown command");
        }
        return 0;
    } catch (const std::exception& e) {
        std::cerr << e.what() << "\n";
        return 2;
    }
}
