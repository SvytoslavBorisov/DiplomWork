#pragma once

#include <atomic>
#include <chrono>
#include <cstdlib>
#include <iostream>
#include <random>
#include <unordered_set>
#include "gost_reduced_model.hpp"
#include "grover_analytic.hpp"
#include "grover_statevector.hpp"
#include "grover_symmetric.hpp"
#include "bbht_adaptive.hpp"
#include "search_runtime.hpp"
#include <algorithm>
#include <cstdint>
#include <stdexcept>
#include <string>
#include <vector>


// Реализует оба способа поиска связывающего блока с сохранением исходного порядка кандидатов и измерений.
namespace herding_link {

using gost_reduced_model::make_context;
using gost_reduced_model::reduced_state_from_hex;
using gost_reduced_model::required_sigma_low64;
using gost_reduced_model::random_state_constrained;
using gost_reduced_model::set_low_sigma_bits;
using grover_analytic::optimal_grover_iterations;

struct LinkResult {
    State block{};
    State state{};
    uint64_t queries = 0;
    bool ok = false;
};

template<class TargetSet,class Key>
inline LinkResult seeded_link(const State& prefix,uint64_t N,int n,int rounds,uint64_t limit,
    int threads,const TargetSet& targets,int s,uint64_t current,uint64_t target,Key key) {
    const auto context=make_context(prefix,N,rounds);
    std::mt19937_64 rng(mix64(requested_seed));
    auto fast_rng=optional_candidate_rng();
    std::vector<State> messages,outputs;
    const uint64_t low=required_sigma_low64(current,target,s);
    WorkerPool pool(threads,std::min<uint64_t>(4096,limit),1024);
    // Увеличивает пакеты от восьми кандидатов для сокращения лишних вычислений и расходов диспетчеризации потоков.

    uint64_t goal=SEARCH_BATCH;
    uint64_t physical=0;
    for(uint64_t offset=0;offset<limit;) {
        const uint64_t batch_size=std::min(goal,limit-offset);
        messages.resize(static_cast<size_t>(batch_size));
        fill_candidates(messages,rng,fast_rng.get(),low,s);
        hash_seeded_batch(context,messages,outputs,threads,&pool);
        physical+=batch_size;
        for(size_t j=0;j<outputs.size();++j)if(targets.find(key(outputs[j],n))!=targets.end()) {
            const uint64_t logical=std::min<uint64_t>(batch_size,((j/SEARCH_BATCH)+1)*SEARCH_BATCH);
            if(std::getenv("NOSTRADAMUS_SEARCH_DEBUG"))std::cerr<<"physical_hash_evaluations="<<physical<<" logical_queries="<<offset+logical<<'\n';
            return {messages[j],outputs[j],offset+logical,true};
        }
        offset+=batch_size;goal=std::min<uint64_t>(4096,goal*2);
    }
    throw std::runtime_error("link not found within trials_limit");
}

inline LinkResult find_link64(const State& prefix, uint64_t N, int n, int rounds, uint64_t limit,
                              int requested_threads, const std::vector<std::string>& targets, int sigma_bits = 0,
                              uint64_t current_sigma = 0, uint64_t target_sigma = 0) {
    const uint64_t required_low = required_sigma_low64(current_sigma, target_sigma, sigma_bits);
    const int nt = workers_for_limit(requested_threads, limit, 1);
    const CompressionContext ctx = make_context(prefix, N, rounds);
    std::unordered_set<uint64_t> targetset;
    targetset.reserve(targets.size() * 2 + 1);
    for (const auto& target : targets) {
        targetset.insert(reduced_key64(reduced_state_from_hex(target, n), n));
    }
    if(has_requested_seed && (nthreads_from(requested_threads)!=1 || requested_rng!="mt19937"))return seeded_link(prefix,N,n,rounds,limit,requested_threads,targetset,sigma_bits,current_sigma,target_sigma,reduced_key64);

    std::atomic<bool> found(false);
    std::vector<uint64_t> completed(static_cast<size_t>(nt), 0);
    LinkResult result;

    auto worker = [&](int tid) {
        const WorkRange range = work_range_for(limit, nt, tid);
        const uint64_t quota = range.end - range.begin;
        uint64_t local_queries = 0;
        std::seed_seq seq{uint32_t(std::random_device{}()),
                          uint32_t(std::chrono::high_resolution_clock::now().time_since_epoch().count()),
                          uint32_t(tid), uint32_t(range.begin), uint32_t(range.begin >> 32)};
        std::mt19937_64 rng(seq);
        if (has_requested_seed) rng.seed(mix64(requested_seed ^ uint64_t(tid) ^ range.begin));
        SearchBatch messages{};
        SearchBatch outputs{};

        while (local_queries < quota && !found.load(std::memory_order_relaxed)) {
            const size_t count = static_cast<size_t>(
                std::min<uint64_t>(SEARCH_BATCH, quota - local_queries));
            for (size_t lane = 0; lane < count; ++lane) messages[lane] = random_state_constrained(rng, required_low, sigma_bits);
            compress_batch(messages, outputs, count, ctx);
            local_queries += count;
            for (size_t lane = 0; lane < count; ++lane) {
                if (targetset.find(reduced_key64(outputs[lane], n)) != targetset.end()) {
                    bool expected = false;
                    if (found.compare_exchange_strong(expected, true,
                                                      std::memory_order_relaxed)) {
                        result.block = messages[lane];
                        result.state = outputs[lane];
                        result.ok = true;
                    }
                    break;
                }
            }
        }
        completed[static_cast<size_t>(tid)] = local_queries;
    };

    std::vector<std::thread> threads;
    threads.reserve(static_cast<size_t>(nt));
    for (int i = 0; i < nt; ++i) threads.emplace_back(worker, i);
    for (auto& x : threads) x.join();
    if (result.ok) { result.queries = sum_completed(completed); return result; }
    throw std::runtime_error("link not found within trials_limit");
}

inline LinkResult find_link_full(const State& prefix, uint64_t N, int n, int rounds, uint64_t limit,
                                 int requested_threads, const std::vector<std::string>& targets, int sigma_bits = 0,
                                 uint64_t current_sigma = 0, uint64_t target_sigma = 0) {
    const uint64_t required_low = required_sigma_low64(current_sigma, target_sigma, sigma_bits);
    const int nt = workers_for_limit(requested_threads, limit, 1);
    const CompressionContext ctx = make_context(prefix, N, rounds);
    std::unordered_set<ReducedKey, ReducedKeyHash> targetset;
    targetset.reserve(targets.size() * 2 + 1);
    for (const auto& target : targets) targetset.insert(reduced_key_full(reduced_state_from_hex(target, n), n));
    if(has_requested_seed && (nthreads_from(requested_threads)!=1 || requested_rng!="mt19937"))return seeded_link(prefix,N,n,rounds,limit,requested_threads,targetset,sigma_bits,current_sigma,target_sigma,reduced_key_full);

    std::atomic<bool> found(false);
    std::vector<uint64_t> completed(static_cast<size_t>(nt), 0);
    LinkResult result;

    auto worker = [&](int tid) {
        const WorkRange range = work_range_for(limit, nt, tid);
        const uint64_t quota = range.end - range.begin;
        uint64_t local_queries = 0;
        std::seed_seq seq{uint32_t(std::random_device{}()),
                          uint32_t(std::chrono::high_resolution_clock::now().time_since_epoch().count()),
                          uint32_t(tid), uint32_t(range.begin), uint32_t(range.begin >> 32)};
        std::mt19937_64 rng(seq);
        if (has_requested_seed) rng.seed(mix64(requested_seed ^ uint64_t(tid) ^ range.begin));
        SearchBatch messages{};
        SearchBatch outputs{};

        while (local_queries < quota && !found.load(std::memory_order_relaxed)) {
            const size_t count = static_cast<size_t>(
                std::min<uint64_t>(SEARCH_BATCH, quota - local_queries));
            for (size_t lane = 0; lane < count; ++lane) messages[lane] = random_state_constrained(rng, required_low, sigma_bits);
            compress_batch(messages, outputs, count, ctx);
            local_queries += count;
            for (size_t lane = 0; lane < count; ++lane) {
                if (targetset.find(reduced_key_full(outputs[lane], n)) != targetset.end()) {
                    bool expected = false;
                    if (found.compare_exchange_strong(expected, true,
                                                      std::memory_order_relaxed)) {
                        result.block = messages[lane];
                        result.state = outputs[lane];
                        result.ok = true;
                    }
                    break;
                }
            }
        }
        completed[static_cast<size_t>(tid)] = local_queries;
    };

    std::vector<std::thread> threads;
    threads.reserve(static_cast<size_t>(nt));
    for (int i = 0; i < nt; ++i) threads.emplace_back(worker, i);
    for (auto& x : threads) x.join();
    if (result.ok) { result.queries = sum_completed(completed); return result; }
    throw std::runtime_error("link not found within trials_limit");
}

inline LinkResult find_link(const std::string& prefix_hex, uint64_t N, int n, int rounds, uint64_t limit,
                            int requested_threads, const std::vector<std::string>& targets, int sigma_bits = 0,
                            uint64_t current_sigma = 0, uint64_t target_sigma = 0) {
    const State prefix = reduced_state_from_hex(prefix_hex, n);
    return n <= 64 ? find_link64(prefix, N, n, rounds, limit, requested_threads, targets, sigma_bits, current_sigma, target_sigma)
                   : find_link_full(prefix, N, n, rounds, limit, requested_threads, targets, sigma_bits, current_sigma, target_sigma);
}

class QuantumTargets {
public:
    QuantumTargets(const std::vector<std::string>& values,int bits): bits_(bits) {
        if(bits<=64 && requested_qram!="generic") {
            small_=std::make_unique<FlatTable64<uint8_t>>(values.size());small_->begin_epoch();
            for(const auto& value:values)small_->insert(reduced_key64(reduced_state_from_hex(value,bits),bits),1);
        }else{
            generic_.reserve(values.size()*2+1);
            for(const auto& value:values)generic_.insert(reduced_key_full(reduced_state_from_hex(value,bits),bits));
        }
    }
    bool contains(const State& output)const {
        return small_?small_->find(reduced_key64(output,bits_))!=nullptr:generic_.find(reduced_key_full(output,bits_))!=generic_.end();
    }
private:
    int bits_;
    std::unique_ptr<FlatTable64<uint8_t>> small_;
    std::unordered_set<ReducedKey,ReducedKeyHash> generic_;
};

struct QuantumLinkResult {
    State block{};
    State target{};
    uint64_t oracle_queries = 0;
    uint64_t simulator_evaluations = 0;
    uint64_t marked_count = 0;
    double success_probability = 0.0;
    double norm_error = 0.0;
    bool found = false;
    uint64_t statevector_elements_processed = 0;
    uint64_t statevector_iterations = 0;
    uint64_t verification_evaluations = 0;
    double statevector_seconds = 0.0;
    std::vector<bbht_adaptive::Result> search_diagnostics;
};

} // Завершает пространство имён поиска связывающего блока.

// Реализует BBHT над общим пространством допустимых кандидатов ГОСТ.
namespace herding_link_bbht {

struct Result {
    herding_link::QuantumLinkResult link;
    bbht_adaptive::Result search;
    uint64_t candidate_evaluations = 0;
};

inline Result find(
    const std::string& prefix_hex,
    const std::vector<std::string>& target_hex,
    uint64_t search_messages, uint64_t N, int n, int rounds,
    uint64_t seed, int requested_threads,
    int sigma_bits = 0, uint64_t current_sigma = 0, uint64_t target_sigma = 0,
    const bbht_adaptive::Options& options = {}, bool fixed_control = false
) {
    using namespace gost_reduced_model;
    if (target_hex.empty() || !search_messages)
        throw std::runtime_error("BBHT linking: пустые цели или пространство поиска.");
    if (!fixed_control) {
        bbht_adaptive::effective_max_attempts(search_messages, options.growth, options.max_attempts);
        if (!options.max_oracle_queries) throw std::runtime_error("BBHT: предел запросов должен быть положительным.");
    }
    const auto dense_limit = fixed_control ? grover_oracle::dense_max_states : options.dense_max_states;
    if (search_messages <= dense_limit)
        grover_statevector::check_resources(search_messages, 0, 262144 + target_hex.size() * 256);
    else grover_oracle::check_resources(search_messages, 262144 + target_hex.size() * 256);
    if (search_messages > std::numeric_limits<size_t>::max())
        throw std::runtime_error("BBHT linking: candidate mask cannot fit address space");
    const uint64_t low = required_sigma_low64(current_sigma, target_sigma, sigma_bits);
    const auto context = make_context(reduced_state_from_hex(prefix_hex, n), N, rounds);
    const herding_link::QuantumTargets targets(target_hex, n);
    auto message_for_index = [&](uint64_t index) {
        State block{};
        block[0] = mix64(index + seed);
        for (size_t word = 1; word < block.size(); ++word)
            block[word] = mix64(index ^ seed ^ (0x9e3779b97f4a7c15ULL * word));
        set_low_sigma_bits(block, low, sigma_bits);
        return block;
    };
    grover_oracle::MarkedSpace marked(search_messages, dense_limit, 262144 + target_hex.size() * 256);
    std::vector<State> outputs;
    WorkerPool pool(requested_threads, std::min<uint64_t>(4096, search_messages), 1024);
    const auto started = std::chrono::steady_clock::now();
    grover_oracle::Deadline fixed_deadline(search_messages > dense_limit);
    auto check_deadline = [&]() {
        if(fixed_control) fixed_deadline.check();
        if(!fixed_control && options.max_stage_seconds > 0 &&
           std::chrono::duration<double>(std::chrono::steady_clock::now()-started).count()
           > options.max_stage_seconds) throw std::runtime_error("BBHT linking: stage timeout");
    };
    for (uint64_t index = 0; index < search_messages;) {
        const size_t count = static_cast<size_t>(std::min<uint64_t>(4096, search_messages - index));
        outputs.resize(count);
        pool.run(count, 1024, [&](WorkRange range) {
            SearchBatch messages{}, hashes{};
            for (uint64_t i = range.begin; i < range.end;) {
                const size_t batch = static_cast<size_t>(std::min<uint64_t>(SEARCH_BATCH, range.end - i));
                for (size_t lane = 0; lane < batch; ++lane)
                    messages[lane] = message_for_index(index + i + lane);
                compress_batch(messages, hashes, batch, context);
                for (size_t lane = 0; lane < batch; ++lane)
                    outputs[static_cast<size_t>(i + lane)] = hashes[lane];
                i += batch;
            }
        });
        for (size_t lane = 0; lane < count; ++lane)
            if (targets.contains(outputs[lane])) marked.add(index + lane);
        check_deadline();
        index += count;
    }
    Result result;
    result.candidate_evaluations = search_messages;
    std::mt19937_64 rng(mix64(seed ^ 0xa5a5a5a5a5a5a5a5ULL));
    State measured_output{};
    auto verify = [&](size_t index) {
        measured_output = compress_with_context(message_for_index(index), context);
        return targets.contains(measured_output);
    };
    result.search = fixed_control
        ? bbht_adaptive::fixed_single(marked, rng, verify)
        : bbht_adaptive::search(marked, rng, verify, options);
    result.link.search_diagnostics.push_back(result.search);
    result.link.oracle_queries = result.search.oracle_queries;
    result.link.simulator_evaluations = search_messages + result.search.verification_queries;
    result.link.verification_evaluations = result.search.verification_queries;
    result.link.marked_count = result.search.marked_count_diagnostic;
    result.link.success_probability = result.search.attempts
        ? result.search.success_probability_sum / result.search.attempts : 0.0;
    result.link.norm_error = result.search.norm_error_max;
    result.link.statevector_elements_processed = result.search.statevector_elements_processed;
    result.link.statevector_iterations = result.search.statevector_iterations;
    result.link.statevector_seconds = result.search.statevector_seconds;
    if (result.search.found) {
        result.link.block = message_for_index(result.search.measured_index);
        result.link.target = measured_output;  // Возвращает уже проверенное состояние без скрытого дополнительного вычисления.
        result.link.found = true;
    }
    check_deadline();
    return result;
}

} // namespace herding_link_bbht

namespace herding_link {
inline QuantumLinkResult find_quantum_link(
    const std::string& prefix, const std::vector<std::string>& targets,
    uint64_t S, uint64_t N, int n, int rounds, uint64_t seed, int threads,
    int sigma_bits = 0, uint64_t current_sigma = 0, uint64_t target_sigma = 0) {
    return herding_link_bbht::find(prefix,targets,S,N,n,rounds,seed,threads,
        sigma_bits,current_sigma,target_sigma,{},true).link;
}
}
