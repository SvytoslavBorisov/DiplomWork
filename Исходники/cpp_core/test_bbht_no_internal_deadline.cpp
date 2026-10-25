#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <random>
#include <stdexcept>
#include <vector>
#include "bbht_dense_statevector.hpp"
#include "bbht_adaptive.hpp"

static void require(bool value, const char* message) {
    if (!value) throw std::runtime_error(message);
}
int main() {
    try {
        // The original statevector would hit its hard-coded Deadline here.
#ifdef _WIN32
        require(_putenv_s("GROVER_TIMEOUT_SECONDS", "0.000001") == 0, "set env failed");
#else
        require(setenv("GROVER_TIMEOUT_SECONDS", "0.000001", 1) == 0, "set env failed");
#endif
        std::vector<uint8_t> marked(8192, 0);
        marked[125] = 1;
        std::mt19937_64 rng1(7), rng2(7);
        const auto run = bbht_dense_statevector::simulate(marked, 72, rng1);
        const auto theoretical = grover_symmetric::simulate(marked, 1, 72, rng2);
        require(std::abs(run.success_probability - theoretical.success_probability) < 1e-11,
                "BBHT no-deadline dense search differs from compact numerical simulator");
        require(run.iterations == 72 && run.oracle_queries == 73,
                "BBHT dense query accounting changed");
        bbht_adaptive::Options options;
        options.max_attempts = 1;
        options.max_oracle_queries = 400;
        options.dense_max_states = 8192;
        const auto result = bbht_adaptive::fixed_repeated(marked, 72, rng2,
            [&](size_t index) {return marked[index] != 0;}, options);
        require(result.attempts == 1 && result.phase_oracle_queries == 72,
                "Fixed BBHT dense search unexpectedly stopped");
        std::cout << "PASS: BBHT dense has no internal deadline; probabilities and queries match\n";
        return 0;
    } catch (const std::exception& ex) {
        std::cerr << "FAIL: " << ex.what() << '\n';
        return 1;
    }
}
