// Одинаковые проверки выполняются с текущим модулем и сохранённым исходным ядром.
#ifdef GOST_MODEL_TEST_CORE_SOURCE
#define main gost_core_command_main
#include GOST_MODEL_TEST_CORE_SOURCE
#undef main
#else
#include "gost_reduced_model.hpp"
#include "gost_reduced_model.hpp"
using namespace gost_reduced_model;
const LpsTable* reduced_model_table_from_other_tu();
State reduced_model_compress_from_other_tu(const State&, const State&, uint64_t, int);
#endif

#include <iostream>
#include <limits>
#include <random>

static uint64_t digest = 14695981039346656037ULL;
static void record(uint64_t value) {
    for (int byte = 0; byte < 8; ++byte) {
        digest ^= (value >> (8 * byte)) & 255;
        digest *= 1099511628211ULL;
    }
}
static void record(const State& value) { for (uint64_t word : value) record(word); }
static void require(bool valid, const char* message) {
    if (!valid) throw std::runtime_error(message);
}

int main() {
    try {
        std::mt19937_64 rng(0x53545249424f4755ULL);
        size_t compression_cases = 0, reduced_cases = 0, sigma_cases = 0;
        for (int rounds = 1; rounds <= 12; ++rounds) {
            for (int sample = 0; sample < 64; ++sample) {
                const State h = random_state(rng), m = random_state(rng);
                const uint64_t N = sample == 0 ? 0 : sample == 1 ? 512 : rng();
                State n{}; n[7] = N;
                const State out = compress_state(m, h, N, rounds);
                require(out == compress_with_context(m, make_context(h, n, rounds)), "N embedding");
#ifndef GOST_MODEL_TEST_CORE_SOURCE
                require(out == reduced_model_compress_from_other_tu(m, h, N, rounds), "second translation unit");
#endif
                record(out);
                const State wide_n = random_state(rng);
                record(compress_with_context(m, make_context(h, wide_n, rounds)));
                compression_cases += 2;
            }
        }
        for (int n : {4, 8, 12, 24, 32, 64, 128, 256, 512}) {
            for (int sample = 0; sample < 64; ++sample) {
                const State h = random_state(rng), m = random_state(rng);
                const std::string hex = reduced_state_to_hex(h, n);
                const State embedded = reduced_state_from_hex(hex, n);
                require(reduced_state_to_hex(embedded, n) == hex, "reduced state round trip");
                State expected{};
                const int words = n / 64, rem = n % 64;
                for (int i = 0; i < words; ++i) expected[i] = h[i];
                if (rem) expected[words] = h[words] & (~uint64_t{0} << (64 - rem));
                require(embedded == expected, "zero padding and first n bits");
                const State out = compress_state(m, embedded, 1024, 12);
                const std::string reduced = reduced_state_to_hex(out, n);
                for (size_t i = 0; i < reduced.size(); ++i) {
                    const int shift = 60 - static_cast<int>((i * 4) % 64);
                    require(hex_value(reduced[i]) == ((out[i / 16] >> shift) & 15), "output truncation");
                }
                record(embedded); record(out);
                ++reduced_cases;
            }
        }
        const uint64_t maximum = std::numeric_limits<uint64_t>::max();
        for (int s : {0, 1, 8, 16, 24, 32, 64}) {
            // Вычисляет ожидаемую маску без сдвига на ширину слова.
            const uint64_t mask = s == 0 ? 0 : maximum >> (64 - s);
            require(sigma_mask64(s) == mask, "sigma mask endpoints");
            for (uint64_t current : {uint64_t{0}, uint64_t{1}, mask, mask / 2, maximum}) {
                for (uint64_t target : {uint64_t{0}, uint64_t{1}, mask, mask / 2, maximum}) {
                    const uint64_t low = required_sigma_low64(current, target, s);
                    require(low == ((target - current) & mask), "sigma modular difference");
                    require(((current + low) & mask) == (target & mask), "sigma update and overflow");
                    const State original = random_state(rng);
                    State block = original;
                    set_low_sigma_bits(block, low, s);
                    for (size_t i = 0; i < 7; ++i) require(block[i] == original[i], "sigma changes high words");
                    require((block[7] & ~mask) == (original[7] & ~mask), "sigma changes high bits");
                    require((block[7] & mask) == low, "sigma low bits");
                    std::mt19937_64 legacy(731), constrained(731);
                    for (int repeat = 0; repeat < 8; ++repeat) {
                        State expected = random_state(legacy);
                        expected[7] = (expected[7] & ~mask) | low;
                        const State generated = random_state_constrained(constrained, low, s);
                        require(generated == expected, "constrained candidate stream");
                        record(generated);
                    }
                    require(legacy() == constrained(), "generator call count");
                    record(block); record(low);
                    ++sigma_cases;
                }
            }
        }
        for (int invalid : {-1, 65}) {
            bool rejected = false;
            try { sigma_mask64(invalid); } catch (const std::runtime_error&) { rejected = true; }
            require(rejected, "invalid sigma width");
        }
#ifndef GOST_MODEL_TEST_CORE_SOURCE
        require(reduced_model_table_from_other_tu() == &LPS_TABLE, "inline table ODR identity");
#endif
        std::cout << "MODEL PASS compression=" << compression_cases
                  << " reduced=" << reduced_cases << " sigma=" << sigma_cases
                  << " digest=" << std::hex << digest << '\n';
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
