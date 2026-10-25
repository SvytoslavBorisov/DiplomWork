#include "quantum_diamond_bbht.hpp"
#include <iostream>

static void require(bool ok, const char* message) {
    if (!ok) throw std::runtime_error(message);
}

static void probabilities() {
    for (size_t S : {size_t{1}, size_t{2}, size_t{9}, size_t{16}, size_t{25}}) {
        for (size_t M = 0; M <= S; ++M) {
            std::vector<uint8_t> mask(S);
            std::fill_n(mask.begin(), M, uint8_t{1});
            for (uint64_t j = 0; j < 12; ++j) {
                std::mt19937_64 a(71), b(71);
                const auto dense = bbht_dense_statevector::simulate(mask, j, a);
                const auto symmetric = grover_symmetric::simulate(mask, M, j, b);
                const double theta = std::asin(std::sqrt(double(M) / S));
                const double expected = std::pow(std::sin((2 * j + 1) * theta), 2);
                require(std::abs(dense.success_probability - expected) < 1e-11,
                        "dense probability differs from Grover formula");
                require(std::abs(symmetric.success_probability - expected) < 1e-11,
                        "symmetric probability differs from Grover formula");
                require(dense.oracle_queries == j + 1 && symmetric.oracle_queries == j + 1,
                        "measurement verification charged incorrectly");
            }
        }
    }
}

static void budgets() {
    for (uint64_t threshold : {uint64_t{0}, uint64_t{8192}}) {
        for (bool fixed : {false, true}) {
            bbht_adaptive::Options options;
            options.dense_max_states = threshold;
            for (uint64_t budget : {uint64_t{1}, uint64_t{7}, uint64_t{100000}}) {
                options.max_oracle_queries = budget;
                std::vector<uint8_t> empty(16);
                std::mt19937_64 rng(42);
                uint64_t verifications = 0;
                auto verify = [&](size_t) { ++verifications; return false; };
                const auto result = fixed
                    ? bbht_adaptive::fixed_repeated(empty, 3, rng, verify, options)
                    : bbht_adaptive::search(empty, rng, verify, options);
                require(!result.found && result.exhausted, "empty space accepted");
                require(result.attempts == verifications && result.failures == verifications,
                        "failed measurements not charged");
                require(result.oracle_queries <= budget, "query cap exceeded");
                require(result.oracle_queries == result.phase_oracle_queries + verifications,
                        "phase or verification queries lost");
                if (budget == 100000) {
                    require(result.attempts == (fixed ? 128 : bbht_adaptive::effective_max_attempts(16,options.growth,options.max_attempts)), "Не соблюдён фактический лимит попыток.");
                    if (fixed) require(result.oracle_queries == 512, "fixed empty cost differs");
                }
                if (fixed && budget == 7)
                    require(result.attempts == 1 && result.oracle_queries == 4,
                            "unfinished fixed attempt charged");
            }
            options.max_oracle_queries = 4;
            std::vector<uint8_t> all(16, 1);
            std::mt19937_64 rng(4);
            const auto result = fixed
                ? bbht_adaptive::fixed_repeated(all, 3, rng, [](size_t) { return true; }, options)
                : bbht_adaptive::search(all, rng, [](size_t) { return true; }, options);
            require(result.found && result.attempts == 1 && result.failures == 0,
                    "all-marked case failed");
            require(result.oracle_queries == (fixed ? 4 : 1), "exact budget rejected");
        }
    }
}

static void layer_accounting() {
    for (bool fixed : {false, true}) {
        bbht_adaptive::Options options;
        const auto result = quantum_diamond_bbht::build_layer(
            {"00000001", "00000002", "00000003", "00000004"},
            1, 1, 2, 1024, 32, 12, 97, 1, 4, 1, 3, options, fixed);
        require(result.searches.size() == 8, "wrong number of fresh search spaces");
        uint64_t queries = 0, attempts = 0;
        for (const auto& search : result.searches) {
            require(search.marked_count == 0 && search.exhausted && !search.found,
                    "empty layer fixture changed");
            const auto expected = fixed ? 1 : bbht_adaptive::effective_max_attempts(1,options.growth,options.max_attempts);
            require(search.attempts == expected && search.failed_attempts == expected,
                    "empty layer repetitions lost");
            queries += search.oracle_queries;
            attempts += search.attempts;
        }
        require(result.layer.qram_entries == 4, "qRAM charged more than once");
        require(result.layer.oracle_queries == 4 + queries, "layer query accounting differs");
        require(result.layer.simulator_evaluations == 4 + 8 + attempts,
                "classical enumeration or verification lost");
        require(result.failures == attempts && result.exhausted_searches == 8,
                "failed searches omitted");
    }
}

static void growth_validation() {
    for (double growth : {1.0, 4.0 / 3.0, 1.5, 4.0}) {
        bbht_adaptive::Options options;
        options.growth = growth;
        std::mt19937_64 rng(7);
        bool rejected = false;
        try {
            bbht_adaptive::search(std::vector<uint8_t>(4, 1), rng,
                                  [](size_t) { return true; }, options);
        } catch (const std::runtime_error&) { rejected = true; }
        require(rejected, "growth outside proven BBHT range accepted");
    }
}

static void fixed_blind_spot() {
    for (uint64_t threshold : {uint64_t{0}, uint64_t{8192}}) {
        bbht_adaptive::Options options;
        options.dense_max_states = threshold;
        std::vector<uint8_t> marked{1, 1, 1, 0};
        std::mt19937_64 first(71), second(71);
        const auto fixed = bbht_adaptive::fixed_repeated(marked, 1, first,
            [&](size_t j) { return marked[j] != 0; }, options);
        require(!fixed.found && fixed.exhausted && fixed.failures == 128,
                "fixed Grover blind spot bypassed");
        require(fixed.oracle_queries == 256, "fixed blind spot cost lost");
        const auto adaptive = bbht_adaptive::search(marked, second,
            [&](size_t j) { return marked[j] != 0; }, options);
        require(adaptive.found, "BBHT failed at fixed Grover blind spot");
    }
}

int main() {
    try {
        probabilities();
        budgets();
        layer_accounting();
        fixed_blind_spot();
        growth_validation();
        std::cout << "PASS: Grover probabilities, 128 retries, budgets, qRAM, growth\n";
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
