#pragma once
#include <array>
#include <cstdint>
#include <limits>

// Реализует общедоступный xoshiro256** 1.0 Дэвида Блэкмана и Себастьяно Виньи.
// Исходный алгоритм опубликован по адресу https://prng.di.unimi.it/xoshiro256starstar.c.
// SplitMix64 инициализирует четыре слова состояния генератора.
class Xoshiro256ss {
public:
    using result_type=uint64_t;
    explicit Xoshiro256ss(uint64_t seed) {
        for(auto& word:state_){seed+=0x9e3779b97f4a7c15ULL;uint64_t z=seed;z=(z^(z>>30))*0xbf58476d1ce4e5b9ULL;z=(z^(z>>27))*0x94d049bb133111ebULL;word=z^(z>>31);}
    }
    explicit Xoshiro256ss(std::array<uint64_t,4> state):state_(state){}
    static constexpr uint64_t min(){return 0;}
    static constexpr uint64_t max(){return std::numeric_limits<uint64_t>::max();}
    uint64_t operator()()noexcept {
        const uint64_t result=rotate(state_[1]*5,7)*9,t=state_[1]<<17;
        state_[2]^=state_[0];state_[3]^=state_[1];state_[1]^=state_[2];state_[0]^=state_[3];state_[2]^=t;state_[3]=rotate(state_[3],45);
        return result;
    }
    void jump()noexcept {
        const std::array<uint64_t,4> constants{0x180ec6d33cfd0abaULL,0xd5a61266f0c9392cULL,0xa9582618e03fc9aaULL,0x39abdc4529b1661cULL};
        std::array<uint64_t,4> result{};
        for(auto polynomial:constants)for(int bit=0;bit<64;++bit){if(polynomial&(uint64_t{1}<<bit))for(size_t i=0;i<4;++i)result[i]^=state_[i];(*this)();}
        state_=result;
    }
private:
    static uint64_t rotate(uint64_t value,int bits)noexcept{return (value<<bits)|(value>>(64-bits));}
    std::array<uint64_t,4> state_{};
};
