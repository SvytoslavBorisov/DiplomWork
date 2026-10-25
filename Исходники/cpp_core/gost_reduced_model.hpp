#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <stdexcept>
#include <string>

namespace gost_reduced_model {

using std::size_t;
using std::uint8_t;
using std::uint64_t;
using State = std::array<uint64_t, 8>;
inline constexpr uint8_t SBOX[256] = {
252,238,221,17,207,110,49,22,251,196,250,218,35,197,4,77,233,119,240,219,147,46,153,186,23,54,241,187,20,205,95,193,249,24,101,90,226,92,239,33,129,28,60,66,139,1,142,79,5,132,2,174,227,106,143,160,6,11,237,152,127,212,211,31,235,52,44,81,234,200,72,171,242,42,104,162,253,58,206,204,181,112,14,86,8,12,118,18,191,114,19,71,156,183,93,135,21,161,150,41,16,123,154,199,243,145,120,111,157,158,178,177,50,117,25,61,255,53,138,126,109,84,198,128,195,189,13,87,223,245,36,169,62,168,67,201,215,121,214,246,124,34,185,3,224,15,236,222,122,148,176,188,220,232,40,80,78,51,10,74,167,151,96,115,30,0,98,68,26,184,56,130,100,159,38,65,173,69,70,146,39,94,85,47,140,163,165,125,105,213,149,59,7,88,179,64,134,172,29,247,48,55,107,228,136,217,231,137,225,27,131,73,76,63,248,254,141,83,170,144,202,216,133,97,32,113,103,164,45,43,9,91,203,155,37,208,190,229,108,82,89,166,116,210,230,244,180,192,209,102,175,194,57,75,99,182};

inline constexpr uint64_t LBOX[64] = {
0x8e20faa72ba0b470ULL,0x47107ddd9b505a38ULL,0xad08b0e0c3282d1cULL,0xd8045870ef14980eULL,
0x6c022c38f90a4c07ULL,0x3601161cf205268dULL,0x1b8e0b0e798c13c8ULL,0x83478b07b2468764ULL,
0xa011d380818e8f40ULL,0x5086e740ce47c920ULL,0x2843fd2067adea10ULL,0x14aff010bdd87508ULL,
0x0ad97808d06cb404ULL,0x05e23c0468365a02ULL,0x8c711e02341b2d01ULL,0x46b60f011a83988eULL,
0x90dab52a387ae76fULL,0x486dd4151c3dfdb9ULL,0x24b86a840e90f0d2ULL,0x125c354207487869ULL,
0x092e94218d243cbaULL,0x8a174a9ec8121e5dULL,0x4585254f64090fa0ULL,0xaccc9ca9328a8950ULL,
0x9d4df05d5f661451ULL,0xc0a878a0a1330aa6ULL,0x60543c50de970553ULL,0x302a1e286fc58ca7ULL,
0x18150f14b9ec46ddULL,0x0c84890ad27623e0ULL,0x0642ca05693b9f70ULL,0x0321658cba93c138ULL,
0x86275df09ce8aaa8ULL,0x439da0784e745554ULL,0xafc0503c273aa42aULL,0xd960281e9d1d5215ULL,
0xe230140fc0802984ULL,0x71180a8960409a42ULL,0xb60c05ca30204d21ULL,0x5b068c651810a89eULL,
0x456c34887a3805b9ULL,0xac361a443d1c8cd2ULL,0x561b0d22900e4669ULL,0x2b838811480723baULL,
0x9bcf4486248d9f5dULL,0xc3e9224312c8c1a0ULL,0xeffa11af0964ee50ULL,0xf97d86d98a327728ULL,
0xe4fa2054a80b329cULL,0x727d102a548b194eULL,0x39b008152acb8227ULL,0x9258048415eb419dULL,
0x492c024284fbaec0ULL,0xaa16012142f35760ULL,0x550b8e9e21f7a530ULL,0xa48b474f9ef5dc18ULL,
0x70a6a56e2440598eULL,0x3853dc371220a247ULL,0x1ca76e95091051adULL,0x0edd37c48a08a6d8ULL,
0x07e095624504536cULL,0x8d70c431ac02a736ULL,0xc83862965601dd1bULL,0x641c314b2b8ee083ULL};

inline constexpr std::array<State, 12> ROUND_C = {{
{{0xb1085bda1ecadae9ULL,0xebcb2f81c0657c1fULL,0x2f6a76432e45d016ULL,0x714eb88d7585c4fcULL,0x4b7ce09192676901ULL,0xa2422a08a460d315ULL,0x05767436cc744d23ULL,0xdd806559f2a64507ULL}},
{{0x6fa3b58aa99d2f1aULL,0x4fe39d460f70b5d7ULL,0xf3feea720a232b98ULL,0x61d55e0f16b50131ULL,0x9ab5176b12d69958ULL,0x5cb561c2db0aa7caULL,0x55dda21bd7cbcd56ULL,0xe679047021b19bb7ULL}},
{{0xf574dcac2bce2fc7ULL,0x0a39fc286a3d8435ULL,0x06f15e5f529c1f8bULL,0xf2ea7514b1297b7bULL,0xd3e20fe490359eb1ULL,0xc1c93a376062db09ULL,0xc2b6f443867adb31ULL,0x991e96f50aba0ab2ULL}},
{{0xef1fdfb3e81566d2ULL,0xf948e1a05d71e4ddULL,0x488e857e335c3c7dULL,0x9d721cad685e353fULL,0xa9d72c82ed03d675ULL,0xd8b71333935203beULL,0x3453eaa193e837f1ULL,0x220cbebc84e3d12eULL}},
{{0x4bea6bacad474799ULL,0x9a3f410c6ca92363ULL,0x7f151c1f1686104aULL,0x359e35d7800fffbdULL,0xbfcd1747253af5a3ULL,0xdfff00b723271a16ULL,0x7a56a27ea9ea63f5ULL,0x601758fd7c6cfe57ULL}},
{{0xae4faeae1d3ad3d9ULL,0x6fa4c33b7a3039c0ULL,0x2d66c4f95142a46cULL,0x187f9ab49af08ec6ULL,0xcffaa6b71c9ab7b4ULL,0x0af21f66c2bec6b6ULL,0xbf71c57236904f35ULL,0xfa68407a46647d6eULL}},
{{0xf4c70e16eeaac5ecULL,0x51ac86febf240954ULL,0x399ec6c7e6bf87c9ULL,0xd3473e33197a93c9ULL,0x0992abc52d822c37ULL,0x06476983284a0504ULL,0x3517454ca23c4af3ULL,0x8886564d3a14d493ULL}},
{{0x9b1f5b424d93c9a7ULL,0x03e7aa020c6e4141ULL,0x4eb7f8719c36de1eULL,0x89b4443b4ddbc49aULL,0xf4892bcb929b0690ULL,0x69d18d2bd1a5c42fULL,0x36acc2355951a8d9ULL,0xa47f0dd4bf02e71eULL}},
{{0x378f5a541631229bULL,0x944c9ad8ec165fdeULL,0x3a7d3a1b25894224ULL,0x3cd955b7e00d0984ULL,0x800a440bdbb2ceb1ULL,0x7b2b8a9aa6079c54ULL,0x0e38dc92cb1f2a60ULL,0x7261445183235adbULL}},
{{0xabbedea680056f52ULL,0x382ae548b2e4f3f3ULL,0x8941e71cff8a78dbULL,0x1fffe18a1b336103ULL,0x9fe76702af69334bULL,0x7a1e6c303b7652f4ULL,0x3698fad1153bb6c3ULL,0x74b4c7fb98459cedULL}},
{{0x7bcd9ed0efc889fbULL,0x3002c6cd635afe94ULL,0xd8fa6bbbebab0761ULL,0x2001802114846679ULL,0x8a1d71efea48b9caULL,0xefbacd1d7d476e98ULL,0xdea2594ac06fd85dULL,0x6bcaa4cd81f32d1bULL}},
{{0x378ee767f11631baULL,0xd21380b00449b17aULL,0xcda43c32bcdf1d77ULL,0xf82012d430219f9bULL,0x5d80ef9d1891cc86ULL,0xe71da4aa88e12852ULL,0xfaf417d5d9b21b99ULL,0x48bc924af11bd720ULL}}
}};

// Таблица T включает подстановку S для каждой позиции входного байта.
// Вычисляет таблицу при компиляции без проверки инициализации в цикле поиска.
using LpsTable = std::array<std::array<uint64_t, 256>, 8>;
inline constexpr LpsTable make_lps_table() {
    LpsTable n{};
    for (int pos = 0; pos < 8; ++pos) {
        for (int x = 0; x < 256; ++x) {
            const uint8_t sb = SBOX[x];
            uint64_t acc = 0;
            for (int bit = 0; bit < 8; ++bit) {
                if (sb & (uint8_t(1u) << (7 - bit))) {
                    acc ^= LBOX[pos * 8 + bit];
                }
            }
            n[pos][x] = acc;
        }
    }
    return n;
}
inline constexpr LpsTable LPS_TABLE = make_lps_table();

inline uint8_t byte_be(uint64_t x, int byte_index) noexcept {
    return static_cast<uint8_t>(x >> (56 - 8 * byte_index));
}

// Объединяет S, P и L, сохраняя состояние в восьми 64-битных словах.
inline State LPS(const State& a) noexcept {
    const auto& T = LPS_TABLE;
    State r{};
    for (int out = 0; out < 8; ++out) {
        r[out] = T[0][byte_be(a[0], out)] ^
                 T[1][byte_be(a[1], out)] ^
                 T[2][byte_be(a[2], out)] ^
                 T[3][byte_be(a[3], out)] ^
                 T[4][byte_be(a[4], out)] ^
                 T[5][byte_be(a[5], out)] ^
                 T[6][byte_be(a[6], out)] ^
                 T[7][byte_be(a[7], out)];
    }
    return r;
}

// Объединяет побитовое исключающее ИЛИ с преобразованием раунда без промежуточных массивов.

inline State LPS_XOR(const State& a, const State& b) noexcept {
    const auto& T = LPS_TABLE;
    const uint64_t x0 = a[0] ^ b[0];
    const uint64_t x1 = a[1] ^ b[1];
    const uint64_t x2 = a[2] ^ b[2];
    const uint64_t x3 = a[3] ^ b[3];
    const uint64_t x4 = a[4] ^ b[4];
    const uint64_t x5 = a[5] ^ b[5];
    const uint64_t x6 = a[6] ^ b[6];
    const uint64_t x7 = a[7] ^ b[7];
    State r{};
    for (int out = 0; out < 8; ++out) {
        r[out] = T[0][byte_be(x0, out)] ^
                 T[1][byte_be(x1, out)] ^
                 T[2][byte_be(x2, out)] ^
                 T[3][byte_be(x3, out)] ^
                 T[4][byte_be(x4, out)] ^
                 T[5][byte_be(x5, out)] ^
                 T[6][byte_be(x6, out)] ^
                 T[7][byte_be(x7, out)];
    }
    return r;
}

struct CompressionContext {
    State h{};
    std::array<State, 12> round_keys{};
    State final_key{};
    int rounds = 12;
};

// Расписание ключей зависит от h, N и числа раундов и переиспользуется для всех блоков кандидатов.

inline CompressionContext make_context(const State& h, const State& n, int rounds) {
    if (rounds < 1 || rounds > 12) throw std::runtime_error("rounds must be 1..12");
    CompressionContext ctx{};
    ctx.h = h;
    ctx.rounds = rounds;

    State K = LPS_XOR(h, n);
    for (int i = 0; i < rounds; ++i) {
        ctx.round_keys[static_cast<size_t>(i)] = K;
        K = LPS_XOR(K, ROUND_C[static_cast<size_t>(i)]);
    }
    ctx.final_key = K;
    return ctx;
}

inline CompressionContext make_context(const State& h, uint64_t N, int rounds) {
    State n{};
    n[7] = N;
    return make_context(h, n, rounds);
}

// Выполняет скалярное сжатие с предварительно вычисленными ключами раундов.

inline State compress_with_context(const State& m, const CompressionContext& ctx) noexcept {
    State state = m;
    for (int i = 0; i < ctx.rounds; ++i) {
        state = LPS_XOR(ctx.round_keys[static_cast<size_t>(i)], state);
    }

    State out{};
    for (size_t i = 0; i < 8; ++i) {
        out[i] = ctx.final_key[i] ^ state[i] ^ ctx.h[i] ^ m[i];
    }
    return out;
}

inline State compress_state(const State& m, const State& h, uint64_t N, int rounds) {
    return compress_with_context(m, make_context(h, N, rounds));
}

inline int hex_value(char c) {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    throw std::runtime_error("invalid hex character");
}

// Восстанавливает состояние из первых n бит части хэш-кода, заполняя остальные биты нулями.
inline State reduced_state_from_hex(const std::string& s, int n) {
    if (n <= 0 || n > 512 || (n % 4) != 0) throw std::runtime_error("n must be multiple of 4 in 4..512");
    if (s.size() != static_cast<size_t>(n / 4)) throw std::runtime_error("bad reduced state length");
    State out{};
    for (size_t nib = 0; nib < s.size(); ++nib) {
        const uint64_t v = static_cast<uint64_t>(hex_value(s[nib]));
        const size_t bit = nib * 4;
        const size_t word = bit / 64;
        const int shift = 60 - static_cast<int>(bit % 64);
        out[word] |= v << shift;
    }
    return out;
}

inline std::string reduced_state_to_hex(const State& s, int n) {
    const size_t nhex = static_cast<size_t>(n / 4);
    static constexpr char HEX[] = "0123456789abcdef";
    std::string out(nhex, '0');
    for (size_t nib = 0; nib < nhex; ++nib) {
        const size_t bit = nib * 4;
        const size_t word = bit / 64;
        const int shift = 60 - static_cast<int>(bit % 64);
        out[nib] = HEX[(s[word] >> shift) & 0xfu];
    }
    return out;
}

// Часть контрольной суммы содержит младшие s бит State[7] при s ≤ 64.

inline uint64_t sigma_mask64(int s) {
    if (s < 0 || s > 64) throw std::runtime_error("sigma bits must be in 0..64");
    if (s == 0) return 0;
    if (s == 64) return ~uint64_t{0};
    return (uint64_t{1} << s) - 1;
}

inline uint64_t required_sigma_low64(uint64_t current_sigma, uint64_t target_sigma, int s) {
    const uint64_t mask = sigma_mask64(s);
    return (target_sigma - current_sigma) & mask;
}

inline void set_low_sigma_bits(State& block, uint64_t required_low, int s) {
    if (s == 0) return;
    const uint64_t mask = sigma_mask64(s);
    block[7] = (block[7] & ~mask) | (required_low & mask);
}

template<class Generator> inline State random_state(Generator& rng) noexcept {
    State s{};
    for (uint64_t& x : s) x = rng();
    return s;
}

template<class Generator> inline State random_state_constrained(Generator& rng, uint64_t required_low, int s) noexcept {
    State block = random_state(rng);
    if (s != 0) {
        const uint64_t mask = s == 64 ? ~uint64_t{0} : ((uint64_t{1} << s) - 1);
        block[7] = (block[7] & ~mask) | (required_low & mask);
    }
    return block;
}

}
