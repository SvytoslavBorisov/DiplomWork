#pragma once

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <stdexcept>
#include <vector>
#include "grover_statevector.hpp"

// Хранит малый оракул маской, а большой оракул упорядоченными индексами реальных решений.
namespace grover_oracle {
inline constexpr uint64_t dense_max_states = 8192;
inline constexpr uint64_t batch_states = 4096;

inline void check_resources(uint64_t states, uint64_t other_bytes = 0) {
    if (!states || states > std::numeric_limits<size_t>::max())
        throw std::runtime_error("Пространство кандидатов превышает лимит адресации.");
    if (other_bytes > grover_statevector::current_limits().max_memory_bytes)
        throw std::runtime_error("Оценка рабочих буферов и qRAM превышает лимит памяти.");
}

class Deadline {
public:
    explicit Deadline(bool scalable): start_(std::chrono::steady_clock::now()) {
        if (!scalable) seconds_ = grover_statevector::current_limits().timeout_seconds;
        else if (const char* raw = std::getenv("GROVER_TIMEOUT_SECONDS")) {
            seconds_ = std::stod(raw);
            if (!std::isfinite(seconds_) || seconds_ <= 0)
                throw std::runtime_error("Время симуляции должно быть положительным.");
        }
    }
    void check() const {
        if (seconds_ > 0 && std::chrono::duration<double>(std::chrono::steady_clock::now()-start_).count() > seconds_)
            throw std::runtime_error("Превышен лимит времени моделирования квантового поиска.");
    }
private:
    std::chrono::steady_clock::time_point start_;
    double seconds_ = 0;
};

class MarkedSpace {
public:
    explicit MarkedSpace(uint64_t states, uint64_t dense_limit = dense_max_states,
                         uint64_t other_bytes = 0): states_(states), dense_(states <= dense_limit) {
        check_resources(states, other_bytes);
        budget_ = grover_statevector::current_limits().max_memory_bytes - other_bytes;
        if (dense_) {
            if (states > budget_) throw std::runtime_error("Маска оракула превышает лимит памяти.");
            mask_.resize(static_cast<size_t>(states));
        }
    }
    size_t size() const { return static_cast<size_t>(states_); }
    bool empty() const { return !states_; }
    uint64_t count() const { return count_; }
    bool dense() const { return dense_; }
    operator const std::vector<uint8_t>&() const { return mask_; }
    bool operator[](size_t index) const {
        return dense_ ? mask_[index] != 0 : std::binary_search(indices_.begin(), indices_.end(), index);
    }
    void add(uint64_t index) {
        if (index >= states_ || (count_ && index <= last_))
            throw std::runtime_error("Индексы помеченных кандидатов должны возрастать внутри пространства.");
        if (dense_) mask_[static_cast<size_t>(index)] = 1;
        else {
            if (indices_.size() == indices_.capacity()) {
                const auto capacity = std::max<size_t>(16, indices_.capacity() * 2);
                if (capacity > budget_ / (2 * sizeof(uint64_t)))
                    throw std::runtime_error("Список решений оракула превышает лимит памяти.");
                indices_.reserve(capacity);
            }
            indices_.push_back(index);
        }
        last_ = index;
        ++count_;
    }
    uint64_t by_rank(uint64_t rank) const {
        if (rank >= count_) throw std::runtime_error("Неверный ранг помеченного кандидата.");
        if (!dense_) return indices_[static_cast<size_t>(rank)];
        for (size_t i = 0; i < mask_.size(); ++i) if (mask_[i] && rank-- == 0) return i;
        throw std::runtime_error("Помеченный кандидат не найден.");
    }
    uint64_t prefix_count(size_t index) const {
        if (!dense_) return static_cast<uint64_t>(std::upper_bound(indices_.begin(), indices_.end(), index)-indices_.begin());
        return static_cast<uint64_t>(std::count(mask_.begin(), mask_.begin()+index+1, uint8_t{1}));
    }
private:
    uint64_t states_, count_ = 0, last_ = 0, budget_ = 0;
    bool dense_;
    std::vector<uint8_t> mask_;
    std::vector<uint64_t> indices_;
};

inline uint64_t count(const MarkedSpace& marked) { return marked.count(); }
inline uint64_t count(const std::vector<uint8_t>& marked) {
    return static_cast<uint64_t>(std::count(marked.begin(), marked.end(), uint8_t{1}));
}
inline uint64_t by_rank(const MarkedSpace& marked, uint64_t rank) { return marked.by_rank(rank); }
inline uint64_t by_rank(const std::vector<uint8_t>& marked, uint64_t rank) {
    for (size_t i = 0; i < marked.size(); ++i) if (marked[i] && rank-- == 0) return i;
    throw std::runtime_error("Помеченный кандидат не найден.");
}
inline uint64_t prefix_count(const MarkedSpace& marked, size_t index) { return marked.prefix_count(index); }
inline uint64_t prefix_count(const std::vector<uint8_t>& marked, size_t index) {
    return static_cast<uint64_t>(std::count(marked.begin(), marked.begin()+index+1, uint8_t{1}));
}
}
