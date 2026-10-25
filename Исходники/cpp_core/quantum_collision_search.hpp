#pragma once

#include <cstdlib>
#include <iostream>
#include <random>
#include <unordered_map>
#include "search_runtime.hpp"
#include "gost_reduced_model.hpp"
#include "grover_analytic.hpp"
#include "grover_statevector.hpp"
#include "grover_symmetric.hpp"
#include "bbht_adaptive.hpp"
#include <algorithm>
#include <cstdint>
#include <chrono>
#include <stdexcept>
#include <string>
#include <vector>

// Реализует квантовый поиск коллизий одного уровня для приложения Ж.


namespace quantum_diamond {

using gost_reduced_model::make_context;
using gost_reduced_model::reduced_state_from_hex;
using gost_reduced_model::required_sigma_low64;
using gost_reduced_model::set_low_sigma_bits;
using grover_analytic::optimal_grover_iterations;

struct QuantumTableEntry {
    size_t vertex = 0;
    State block{};
};

// Хранит все записи qRAM в порядке добавления с общей классической таблицей открытой адресации.

class QuantumQram {
public:
    QuantumQram(uint64_t expected,int bits): bits_(bits) {
        if(bits<=64 && requested_qram!="generic") {
            small_=std::make_unique<FlatTable64<std::vector<QuantumTableEntry>>>(expected);
            small_->begin_epoch();
        } else generic_.reserve(static_cast<size_t>(expected*2+1));
    }
    void insert(const State& output,const QuantumTableEntry& entry) {
        if(small_)small_->get_or_insert(reduced_key64(output,bits_)).push_back(entry);
        else generic_[reduced_key_full(output,bits_)].push_back(entry);
    }
    const std::vector<QuantumTableEntry>* find(const State& output) const {
        if(small_)return small_->find(reduced_key64(output,bits_));
        const auto it=generic_.find(reduced_key_full(output,bits_));
        return it==generic_.end()?nullptr:&it->second;
    }
    bool uses_u64() const { return bool(small_); }
private:
    int bits_;
    std::unique_ptr<FlatTable64<std::vector<QuantumTableEntry>>> small_;
    std::unordered_map<ReducedKey,std::vector<QuantumTableEntry>,ReducedKeyHash> generic_;
};

struct QuantumEdge {
    size_t left = 0;
    size_t right = 0;
    State left_block{};
    State right_block{};
    State common{};
};

struct QuantumLayerResult {
    std::vector<QuantumEdge> edges;
    uint64_t oracle_queries = 0;
    uint64_t simulator_evaluations = 0;
    uint64_t qram_entries = 0;
    uint64_t grover_successes = 0;
    uint64_t statevector_elements_processed = 0;
    uint64_t statevector_iterations = 0;
    uint64_t grover_attempts = 0;
    uint64_t marked_elements = 0;
    uint64_t verification_evaluations = 0;
    double success_probability_sum = 0.0;
    double statevector_norm_error_max = 0.0;
    double statevector_seconds = 0.0;
    std::vector<bbht_adaptive::Result> search_diagnostics;
};

struct QuantumLayerWorkspace {
    std::vector<State> messages,outputs;
    uint64_t reallocations=0;
    bool debug=std::getenv("NOSTRADAMUS_WORKSPACE_DEBUG")!=nullptr;
    void resize_messages(size_t n) {
        if(debug && messages.capacity()<n)++reallocations;
        messages.resize(n);
    }
    void prepare_outputs(size_t n) {
        if(debug && outputs.capacity()<n)++reallocations;
        outputs.resize(n);
    }
};

// Вычисляет переходы общего множества сообщений пакетами по непересекающимся диапазонам потоков.

inline void evaluate_message_space_into(
    const CompressionContext& ctx,
    const std::vector<State>& messages,
    std::vector<State>& outputs,
    int requested_threads,
    WorkerPool* pool=nullptr
) {
    outputs.resize(messages.size());
    if (messages.empty()) return;
    const uint64_t total = static_cast<uint64_t>(messages.size());
    auto worker = [&](WorkRange range) {
        SearchBatch batch_messages{};
        SearchBatch batch_outputs{};
        uint64_t index = range.begin;
        while (index < range.end) {
            const size_t count = static_cast<size_t>(
                std::min<uint64_t>(SEARCH_BATCH, range.end - index));
            for (size_t lane = 0; lane < count; ++lane) {
                batch_messages[lane] = messages[static_cast<size_t>(index + lane)];
            }
            compress_batch(batch_messages, batch_outputs, count, ctx);
            for (size_t lane = 0; lane < count; ++lane) {
                outputs[static_cast<size_t>(index + lane)] = batch_outputs[lane];
            }
            index += count;
        }
    };

    if(pool)pool->run(total,128,worker);
    else parallel_ranges(total,requested_threads,128,worker);
}

// Воспроизводит прежний блок кандидата по его абсолютному индексу без расходования случайных чисел.
inline State indexed_message(uint64_t index, uint64_t seed, uint64_t low, int sigma_bits) {
    State block{};
    block[0] = mix64(index + seed);
    for (size_t word = 1; word < block.size(); ++word)
        block[word] = mix64(index ^ seed ^ (0x9e3779b97f4a7c15ULL * word));
    set_low_sigma_bits(block, low, sigma_bits);
    return block;
}

inline uint64_t layer_working_bytes(uint64_t L, uint64_t S, size_t vertices, uint64_t dense_limit) {
    const auto budget = grover_statevector::current_limits().max_memory_bytes;
    if (vertices > budget / 256 || L > budget / 256 / vertices)
        throw std::runtime_error("Оценка памяти qRAM превышает лимит симулятора.");
    const auto buffers = std::max(L, S <= dense_limit ? S : grover_oracle::batch_states);
    if (buffers > budget / 128) throw std::runtime_error("Рабочие буферы превышают лимит памяти.");
    const auto bytes = 128 * buffers + 256 * L * vertices + 256 * vertices;
    grover_oracle::check_resources(S, bytes);
    return bytes;
}

// Вычисляет весь реальный оракул пакетами и сохраняет только индексы помеченных кандидатов.
template<class Check>
inline grover_oracle::MarkedSpace streamed_oracle(QuantumLayerWorkspace& workspace,
    const CompressionContext& context, const QuantumQram& qram, size_t vertex,
    uint64_t base, uint64_t count, uint64_t seed, uint64_t low, int sigma_bits,
    int threads, WorkerPool& pool, Check&& check, uint64_t other_bytes) {
    grover_oracle::MarkedSpace marked(count, 0, other_bytes);
    for (uint64_t offset = 0; offset < count;) {
        check();
        const auto batch = std::min(grover_oracle::batch_states, count - offset);
        workspace.resize_messages(static_cast<size_t>(batch));
        for (size_t j = 0; j < batch; ++j)
            workspace.messages[j] = indexed_message(base + offset + j, seed, low, sigma_bits);
        evaluate_message_space_into(context, workspace.messages, workspace.outputs, threads, &pool);
        for (size_t j = 0; j < batch; ++j) {
            const auto* found = qram.find(workspace.outputs[j]);
            if (found) for (const auto& item : *found) if (item.vertex != vertex) {
                marked.add(offset + j);
                break;
            }
        }
        offset += batch;
    }
    return marked;
}


}

// Строит один уровень алмазной структуры посредством адаптивного режима BBHT.
namespace quantum_diamond_bbht {

// Сохраняет диагностические показатели каждого поиска на одном уровне алмаза.
struct SearchObservation {
    uint64_t vertex = 0;
    uint64_t repetition = 0;
    uint64_t marked_count = 0;
    bool found = false;
    bool exhausted = false;
    uint64_t oracle_queries = 0;
    uint64_t phase_oracle_queries = 0;
    uint64_t verification_queries = 0;
    uint64_t attempts = 0;
    uint64_t failed_attempts = 0;
    uint64_t search_messages = 0;
    double growth = 1.2;
    uint64_t effective_max_attempts = 0;
    const char* attempt_policy = "bbht_auto";
    const char* stop_reason = "attempt_limit";
};

struct Result {
    quantum_diamond::QuantumLayerResult layer;
    std::vector<SearchObservation> searches;
    uint64_t failures = 0;
    uint64_t exhausted_searches = 0;
    uint64_t successful_searches = 0;
    uint64_t total_searches = 0;
    uint64_t phase_oracle_queries = 0;
    uint64_t verification_queries = 0;
};

inline Result build_layer(
    const std::vector<std::string>& state_hex,
    uint64_t table_messages, uint64_t search_messages, int layer_bits,
    uint64_t N, int n, int rounds, uint64_t seed, int requested_threads,
    int sigma_bits = 0, uint64_t current_sigma = 0, uint64_t target_sigma = 0,
    const bbht_adaptive::Options& options = {}, bool fixed_control = false
) {
    using namespace gost_reduced_model;
    using namespace quantum_diamond;
    if (state_hex.size() < 2 || (state_hex.size() & (state_hex.size() - 1)) ||
        layer_bits < 1 || layer_bits >= 63 ||
        (uint64_t{1} << layer_bits) != state_hex.size() ||
        !table_messages || !search_messages)
        throw std::runtime_error("BBHT diamond: неверные параметры уровня.");
    const uint64_t low = required_sigma_low64(current_sigma, target_sigma, sigma_bits);
    if (!fixed_control) {
        bbht_adaptive::effective_max_attempts(search_messages, options.growth, options.max_attempts);
        if (!options.max_oracle_queries) throw std::runtime_error("BBHT: предел запросов должен быть положительным.");
    }
    const auto dense_limit = fixed_control ? grover_oracle::dense_max_states : options.dense_max_states;
    const auto other_bytes = layer_working_bytes(table_messages, search_messages, state_hex.size(), dense_limit);
    if (search_messages <= dense_limit)
        grover_statevector::check_resources(search_messages, 0, other_bytes);
    const auto started = std::chrono::steady_clock::now();
    grover_oracle::Deadline fixed_deadline(search_messages > dense_limit);
    auto check_deadline = [&]() {
        if (fixed_control) fixed_deadline.check();
        if(!fixed_control && options.max_stage_seconds > 0 &&
           std::chrono::duration<double>(std::chrono::steady_clock::now()-started).count()
           > options.max_stage_seconds) throw std::runtime_error("BBHT diamond: stage timeout");
    };
    std::vector<CompressionContext> contexts;
    contexts.reserve(state_hex.size());
    for (const auto& hex : state_hex)
        contexts.push_back(make_context(reduced_state_from_hex(hex, n), N, rounds));
    std::mt19937_64 rng(seed);
    uint64_t candidate_index = 0;
    QuantumLayerWorkspace workspace;
    WorkerPool pool(requested_threads, std::max(table_messages, search_messages), 128);
    auto create_space = [&](uint64_t count) {
        workspace.resize_messages(static_cast<size_t>(count));
        for (auto& message : workspace.messages) {
            const uint64_t index = candidate_index++;
            State block{};
            block[0] = mix64(index + seed);
            for (size_t word = 1; word < block.size(); ++word)
                block[word] = mix64(index ^ seed ^ (0x9e3779b97f4a7c15ULL * word));
            set_low_sigma_bits(block, low, sigma_bits);
            message = block;
        }
    };
    Result result;
    result.searches.reserve(state_hex.size() * static_cast<size_t>(layer_bits));
    auto& stats = result.layer;
    create_space(table_messages);
    QuantumQram qram(table_messages * state_hex.size(), n);
    for (size_t vertex = 0; vertex < state_hex.size(); ++vertex) {
        check_deadline();
        workspace.prepare_outputs(table_messages);
        evaluate_message_space_into(contexts[vertex], workspace.messages,
                                    workspace.outputs, requested_threads, &pool);
        for (size_t j = 0; j < workspace.outputs.size(); ++j)
            qram.insert(workspace.outputs[j], {vertex, workspace.messages[j]});
    }
    stats.qram_entries = table_messages * state_hex.size();
    stats.simulator_evaluations = stats.qram_entries;
    stats.oracle_queries = stats.qram_entries;
    for (size_t vertex = 0; vertex < state_hex.size(); ++vertex) {
        for (int repetition = 0; repetition < layer_bits; ++repetition) {
            check_deadline();
            const auto base = candidate_index;
            grover_oracle::MarkedSpace marked(search_messages, dense_limit, other_bytes);
            if (marked.dense()) {
                create_space(search_messages);
                workspace.prepare_outputs(search_messages);
                evaluate_message_space_into(contexts[vertex], workspace.messages,
                                            workspace.outputs, requested_threads, &pool);
                for (size_t j = 0; j < search_messages; ++j) {
                    const auto* found = qram.find(workspace.outputs[j]);
                    if (found) for (const auto& item : *found) if (item.vertex != vertex) {
                        marked.add(j);
                        break;
                    }
                }
            } else {
                if (search_messages > UINT64_MAX - candidate_index)
                    throw std::runtime_error("Исчерпан диапазон индексов кандидатов.");
                candidate_index += search_messages;
                marked = streamed_oracle(workspace, contexts[vertex], qram, vertex, base,
                    search_messages, seed, low, sigma_bits, requested_threads, pool, check_deadline, other_bytes);
            }
            stats.simulator_evaluations += search_messages;
            State measured_block{}, measured_output{};
            auto verify = [&](size_t index) {
                measured_block = marked.dense() ? workspace.messages[index]
                    : indexed_message(base + index, seed, low, sigma_bits);
                measured_output = compress_with_context(measured_block, contexts[vertex]);
                if (marked.dense() && measured_output != workspace.outputs[index])
                    throw std::runtime_error("BBHT diamond: ошибка повторного вычисления ГОСТ.");
                const auto* found = qram.find(measured_output);
                if (!found) return false;
                for (const auto& item : *found)
                    if (item.vertex != vertex) return true;
                return false;
            };
            const auto search = fixed_control
                ? bbht_adaptive::fixed_single(marked, rng, verify)
                : bbht_adaptive::search(marked, rng, verify, options);
            stats.search_diagnostics.push_back(search);
            // Диагностика не влияет на выбор кандидатов и состояние генератора случайных чисел.
            result.searches.push_back(SearchObservation{
                static_cast<uint64_t>(vertex), static_cast<uint64_t>(repetition),
                marked.count(),
                search.found, search.exhausted, search.oracle_queries,
                search.phase_oracle_queries, search.verification_queries,
                search.attempts, search.failures, search.search_messages, search.growth,
                search.effective_max_attempts, search.attempt_policy, search.stop_reason
            });
            stats.oracle_queries += search.oracle_queries;
            stats.simulator_evaluations += search.verification_queries;
            stats.verification_evaluations += search.verification_queries;
            stats.grover_attempts += search.attempts;
            stats.marked_elements += search.marked_count_diagnostic;
            stats.success_probability_sum += search.success_probability_sum;
            stats.statevector_norm_error_max = std::max(stats.statevector_norm_error_max, search.norm_error_max);
            stats.statevector_iterations += search.statevector_iterations;
            stats.statevector_elements_processed += search.statevector_elements_processed;
            stats.statevector_seconds += search.statevector_seconds;
            result.phase_oracle_queries += search.phase_oracle_queries;
            result.verification_queries += search.verification_queries;
            result.failures += search.failures;
            result.exhausted_searches += search.exhausted ? 1 : 0;
            ++result.total_searches;
            if (!search.found) continue;
            ++result.successful_searches;
            const auto* matches = qram.find(measured_output);
            if (!matches) throw std::runtime_error("BBHT diamond: не найдено ребро qRAM.");
            const QuantumTableEntry* other = nullptr;
            for (const auto& item : *matches)
                if (item.vertex != vertex) { other = &item; break; }
            if (!other) throw std::runtime_error("BBHT diamond: петля вместо коллизии.");
            QuantumEdge edge{};
            edge.left = vertex;
            edge.right = other->vertex;
            edge.left_block = measured_block;
            edge.right_block = other->block;
            edge.common = measured_output;
            stats.edges.push_back(edge);
            ++stats.grover_successes;
        }
    }
    if(workspace.debug) std::cerr << "workspace_reallocations=" << workspace.reallocations
        << " messages_capacity=" << workspace.messages.capacity() << " outputs_capacity=" << workspace.outputs.capacity() << '\n';
    check_deadline();
    return result;
}

} // namespace quantum_diamond_bbht

namespace quantum_diamond {
inline QuantumLayerResult build_quantum_layer(
    const std::vector<std::string>& states, uint64_t L, uint64_t S, int layer_bits,
    uint64_t N, int n, int rounds, uint64_t seed, int threads,
    int sigma_bits = 0, uint64_t current_sigma = 0, uint64_t target_sigma = 0) {
    return quantum_diamond_bbht::build_layer(states,L,S,layer_bits,N,n,rounds,seed,threads,
        sigma_bits,current_sigma,target_sigma,{},true).layer;
}
}
