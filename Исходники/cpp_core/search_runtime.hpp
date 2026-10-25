#pragma once

#include <algorithm>
#include <array>
#include <cstdint>
#include <exception>
#include <functional>
#include <limits>
#include <memory>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>
#if defined(__AVX2__) || defined(GOST_FORCE_AVX2)
#include <immintrin.h>
#endif
#include <random>
#include "candidate_rng.hpp"
#include "gost_reduced_model.hpp"

using gost_reduced_model::State;
using gost_reduced_model::LPS_TABLE;
using gost_reduced_model::byte_be;
using gost_reduced_model::CompressionContext;
using gost_reduced_model::compress_with_context;

inline std::string requested_qram = "auto";
inline bool has_requested_seed = false;
inline uint64_t requested_seed = 0;

inline std::string requested_rng = "mt19937";



#if defined(__AVX2__) || defined(GOST_FORCE_AVX2)
using Batch4 = std::array<State, 4>;

// Обрабатывает четыре независимых преобразования LPS параллельно через AVX2 без временных массивов байтов.

inline Batch4 LPS_XOR4_same_key(const Batch4& states, const State& key) noexcept {
    const auto& T = LPS_TABLE;
    Batch4 r{};
    alignas(32) uint64_t lanes[4];

    for (int out = 0; out < 8; ++out) {
        __m256i acc = _mm256_setzero_si256();
        for (int pos = 0; pos < 8; ++pos) {
            const long long i0 = static_cast<long long>(byte_be(states[0][static_cast<size_t>(pos)] ^ key[static_cast<size_t>(pos)], out));
            const long long i1 = static_cast<long long>(byte_be(states[1][static_cast<size_t>(pos)] ^ key[static_cast<size_t>(pos)], out));
            const long long i2 = static_cast<long long>(byte_be(states[2][static_cast<size_t>(pos)] ^ key[static_cast<size_t>(pos)], out));
            const long long i3 = static_cast<long long>(byte_be(states[3][static_cast<size_t>(pos)] ^ key[static_cast<size_t>(pos)], out));
            const __m256i idx = _mm256_set_epi64x(i3, i2, i1, i0);
            const __m256i v = _mm256_i64gather_epi64(
                reinterpret_cast<const long long*>(T[static_cast<size_t>(pos)].data()), idx, 8);
            acc = _mm256_xor_si256(acc, v);
        }
        _mm256_store_si256(reinterpret_cast<__m256i*>(lanes), acc);
        for (size_t lane = 0; lane < 4; ++lane) r[lane][static_cast<size_t>(out)] = lanes[lane];
    }
    return r;
}

inline Batch4 compress_batch4(const Batch4& messages, const CompressionContext& ctx) noexcept {
    Batch4 state = messages;
    for (int i = 0; i < ctx.rounds; ++i) {
        state = LPS_XOR4_same_key(state, ctx.round_keys[static_cast<size_t>(i)]);
    }

    Batch4 out{};
    alignas(32) uint64_t lanes[4];
    for (size_t word = 0; word < 8; ++word) {
        const __m256i st = _mm256_set_epi64x(
            static_cast<long long>(state[3][word]), static_cast<long long>(state[2][word]),
            static_cast<long long>(state[1][word]), static_cast<long long>(state[0][word]));
        const __m256i msg = _mm256_set_epi64x(
            static_cast<long long>(messages[3][word]), static_cast<long long>(messages[2][word]),
            static_cast<long long>(messages[1][word]), static_cast<long long>(messages[0][word]));
        const __m256i constant = _mm256_set1_epi64x(
            static_cast<long long>(ctx.final_key[word] ^ ctx.h[word]));
        const __m256i v = _mm256_xor_si256(_mm256_xor_si256(st, msg), constant);
        _mm256_store_si256(reinterpret_cast<__m256i*>(lanes), v);
        for (size_t lane = 0; lane < 4; ++lane) out[lane][word] = lanes[lane];
    }
    return out;
}
#endif

inline constexpr size_t SEARCH_BATCH = 8;
using SearchBatch = std::array<State, SEARCH_BATCH>;

// Обрабатывает до восьми кандидатов пакетами AVX2 со скалярным остатком.

inline void compress_batch(const SearchBatch& messages, SearchBatch& outputs,
                                  size_t count, const CompressionContext& ctx) noexcept {
    size_t done = 0;
#if defined(__AVX2__) || defined(GOST_FORCE_AVX2)
    while (done + 4 <= count) {
        Batch4 in4{};
        for (size_t lane = 0; lane < 4; ++lane) in4[lane] = messages[done + lane];
        const Batch4 out4 = compress_batch4(in4, ctx);
        for (size_t lane = 0; lane < 4; ++lane) outputs[done + lane] = out4[lane];
        done += 4;
    }
#endif
    while (done < count) {
        outputs[done] = compress_with_context(messages[done], ctx);
        ++done;
    }
}

inline uint64_t reduced_key64(const State& s, int n) noexcept {
    return n == 64 ? s[0] : (s[0] >> (64 - n));
}

struct ReducedKey {
    std::array<uint64_t, 8> w{};
    bool operator==(const ReducedKey& other) const noexcept { return w == other.w; }
};

struct ReducedKeyHash {
    size_t operator()(const ReducedKey& k) const noexcept {
        uint64_t h = 0x9e3779b97f4a7c15ULL;
        for (uint64_t x : k.w) {
            x ^= x >> 30; x *= 0xbf58476d1ce4e5b9ULL;
            x ^= x >> 27; x *= 0x94d049bb133111ebULL;
            x ^= x >> 31;
            h ^= x + 0x9e3779b97f4a7c15ULL + (h << 6) + (h >> 2);
        }
        return static_cast<size_t>(h);
    }
};

inline ReducedKey reduced_key_full(const State& s, int n) noexcept {
    ReducedKey k{};
    const int full_words = n / 64;
    const int rem = n % 64;
    for (int i = 0; i < full_words; ++i) k.w[static_cast<size_t>(i)] = s[static_cast<size_t>(i)];
    if (rem) k.w[static_cast<size_t>(full_words)] = s[static_cast<size_t>(full_words)] & (~0ULL << (64 - rem));
    return k;
}

inline int nthreads_from(int requested) {
    if (requested > 0) return requested;
    unsigned n = std::thread::hardware_concurrency();
    if (!n) n = 1;
    return static_cast<int>(std::min<unsigned>(n, 16));
}

struct WorkRange {
    uint64_t begin = 0;
    uint64_t end = 0;
};

// Заранее распределяет лимит по потокам с локальными счётчиками без совместных атомарных операций.

inline WorkRange work_range_for(uint64_t limit, int workers, int tid) noexcept {
    const uint64_t n = static_cast<uint64_t>(workers);
    const uint64_t id = static_cast<uint64_t>(tid);
    const uint64_t base = limit / n;
    const uint64_t extra = limit % n;
    const uint64_t begin = id * base + std::min<uint64_t>(id, extra);
    const uint64_t length = base + (id < extra ? 1ULL : 0ULL);
    return {begin, begin + length};
}

inline int workers_for_limit(int requested, uint64_t limit, uint64_t useful_granularity) noexcept {
    const int wanted = nthreads_from(requested);
    const uint64_t useful = std::max<uint64_t>(1, limit / useful_granularity);
    return static_cast<int>(std::min<uint64_t>(static_cast<uint64_t>(wanted), useful));
}

#include "worker_pool.hpp"

// Координатор сохраняет исходный поток mt19937 и порядок выбора кандидатов.

template<class Work>
inline void parallel_ranges(uint64_t total, int requested, uint64_t grain, Work work) {
    WorkerPool pool(requested,total,grain);
    pool.run(total,grain,work);
}

inline uint64_t mix64(uint64_t x) noexcept {
    x ^= x >> 30;
    x *= 0xbf58476d1ce4e5b9ULL;
    x ^= x >> 27;
    x *= 0x94d049bb133111ebULL;
    x ^= x >> 31;
    return x;
}

inline size_t table_capacity_for(uint64_t expected) {
    size_t cap = 32;
    const uint64_t need = expected > (std::numeric_limits<uint64_t>::max() / 2)
        ? std::numeric_limits<uint64_t>::max()
        : expected * 2;
    while (cap < need) cap <<= 1;
    return cap;
}

template<class Value>
class FlatTable64 {
public:
    explicit FlatTable64(uint64_t expected)
        : slots_(table_capacity_for(expected)), mask_(slots_.size() - 1) {}

    void begin_epoch() {
        ++generation_;
        if (generation_ == 0) {
            for (auto& slot : slots_) slot.generation = 0;
            generation_ = 1;
        }
    }

    void insert(uint64_t key, const Value& message) noexcept {
        size_t idx = static_cast<size_t>(mix64(key)) & mask_;
        for (;;) {
            Entry& slot = slots_[idx];
            if (slot.generation != generation_) {
                slot.key = key;
                slot.message = message;
                slot.generation = generation_;
                return;
            }
            if (slot.key == key) return; // Сохраняет первый блок для ключа.
            idx = (idx + 1) & mask_;
        }
    }

    const Value* find(uint64_t key) const noexcept {
        size_t idx = static_cast<size_t>(mix64(key)) & mask_;
        for (;;) {
            const Entry& slot = slots_[idx];
            if (slot.generation != generation_) return nullptr;
            if (slot.key == key) return &slot.message;
            idx = (idx + 1) & mask_;
        }
    }

    Value& get_or_insert(uint64_t key) {
        size_t idx=static_cast<size_t>(mix64(key)) & mask_;
        for(;;) {
            Entry& slot=slots_[idx];
            if(slot.generation!=generation_) {
                slot.key=key;slot.message=Value{};slot.generation=generation_;
                return slot.message;
            }
            if(slot.key==key)return slot.message;
            idx=(idx+1)&mask_;
        }
    }
private:
    struct Entry {
        uint64_t key = 0;
        Value message{};
        uint32_t generation = 0;
    };
    std::vector<Entry> slots_;
    size_t mask_ = 0;
    uint32_t generation_ = 0;
};

inline void hash_seeded_batch(const CompressionContext& ctx, const std::vector<State>& messages,
                              std::vector<State>& outputs, int requested,WorkerPool* pool=nullptr) {
    outputs.resize(messages.size());
    auto work=[&](WorkRange range) {
        SearchBatch in{},out{};
        for(uint64_t i=range.begin;i<range.end;) {
            const size_t n=static_cast<size_t>(std::min<uint64_t>(SEARCH_BATCH,range.end-i));
            for(size_t lane=0;lane<n;++lane)in[lane]=messages[static_cast<size_t>(i+lane)];
            compress_batch(in,out,n,ctx);
            for(size_t lane=0;lane<n;++lane)outputs[static_cast<size_t>(i+lane)]=out[lane];
            i+=n;
        }
    };
    if(pool)pool->run(messages.size(),1024,work);
    else parallel_ranges(messages.size(),requested,1024,work);
}

inline uint64_t sum_completed(const std::vector<uint64_t>& completed) noexcept {
    uint64_t total = 0;
    for (uint64_t value : completed) total += value;
    return total;
}

// Генерирует кандидаты выбранным генератором случайных чисел.
inline std::unique_ptr<Xoshiro256ss> optional_candidate_rng() {
    return requested_rng=="xoshiro256ss"?std::make_unique<Xoshiro256ss>(mix64(requested_seed)):nullptr;
}
inline void fill_candidates(std::vector<State>& messages,std::mt19937_64& legacy,Xoshiro256ss* fast,uint64_t low,int s) {
    if(fast)for(auto& m:messages)m=gost_reduced_model::random_state_constrained(*fast,low,s);
    else for(auto& m:messages)m=gost_reduced_model::random_state_constrained(legacy,low,s);
}
