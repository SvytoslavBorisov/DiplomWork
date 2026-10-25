#pragma once
// Isolated classical control for the complete herding CLI. Uses the same
// reduced GOST compression, N and checksum constraints, but no Grover oracle.
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <limits>
#include <stdexcept>
#include <string>
#include <unordered_set>
#include <vector>
#include "quantum_diamond.hpp"
#include "herding_link.hpp"

namespace classical_herding_cli {
using namespace gost_reduced_model;
using quantum_diamond::QuantumEdge;
using quantum_diamond::QuantumLayerResult;

inline uint64_t classical_list_size(int n,int r,double scale=1.0) {
    if(n<r || r<1 || scale<=0 || !std::isfinite(scale))
        throw std::runtime_error("Classical diamond: bad n/r/scale");
    const long double value=std::ceil(scale*std::sqrt(std::exp2(static_cast<long double>(n-r)) *
                                             (2.0L*r)));
    if(!std::isfinite(value) || value>static_cast<long double>(std::numeric_limits<uint64_t>::max()))
        throw std::runtime_error("Classical list too large");
    return std::max<uint64_t>(1,static_cast<uint64_t>(value));
}

struct Layer {
    QuantumLayerResult layer;
    uint64_t searches=0;
};
struct Sample {
    uint64_t key;
    uint32_t vertex;
    State block;
    bool operator<(const Sample& rhs) const {return key<rhs.key;}
};
inline State message(uint64_t index,uint64_t seed,int sigma_bits,uint64_t low) {
    State block{};
    block[0]=mix64(index+seed);
    for(size_t word=1;word<block.size();++word)
        block[word]=mix64(index ^ seed ^ (0x9e3779b97f4a7c15ULL*word));
    set_low_sigma_bits(block,low,sigma_bits);
    return block;
}

inline Layer build_layer(const std::vector<std::string>& hex_states,
                         uint64_t samples_per_vertex, uint64_t N,int n,int rounds,
                         uint64_t seed,int threads,int sigma_bits,
                         uint64_t current_sigma,uint64_t target_sigma) {
    if(n>64) throw std::runtime_error("Classical control currently supports n<=64");
    if(hex_states.empty() || !samples_per_vertex || hex_states.size()>(1u<<20) ||
       samples_per_vertex>std::numeric_limits<size_t>::max()/hex_states.size())
        throw std::runtime_error("Classical diamond: invalid sample count");
    const size_t total=static_cast<size_t>(samples_per_vertex*hex_states.size());
    // Explicit safety bound on RAM; unlike Grover it can be raised via env for
    // sufficiently provisioned hardware. Never silently truncate an experiment.
    const auto memory=grover_statevector::current_limits().max_memory_bytes;
    if(total>memory/sizeof(Sample)/2)
        throw std::runtime_error("Classical diamond: sample storage exceeds configured memory safety budget");
    const uint64_t low=required_sigma_low64(current_sigma,target_sigma,sigma_bits);
    std::vector<Sample> samples;
    samples.reserve(total);
    std::vector<State> messages,outputs;
    const uint64_t chunk_size=4096;
    WorkerPool pool(threads,chunk_size,128);
    for(size_t vertex=0;vertex<hex_states.size();++vertex) {
        const auto context=make_context(reduced_state_from_hex(hex_states[vertex],n),N,rounds);
        for(uint64_t offset=0;offset<samples_per_vertex;offset+=chunk_size) {
            const size_t count=static_cast<size_t>(std::min<uint64_t>(chunk_size,samples_per_vertex-offset));
            messages.resize(count);
            for(size_t j=0;j<count;++j)
                messages[j]=message(offset+j,mix64(seed+vertex*0x9e3779b97f4a7c15ULL),sigma_bits,low);
            quantum_diamond::evaluate_message_space_into(context,messages,outputs,threads,&pool);
            for(size_t j=0;j<count;++j)
                samples.push_back({reduced_key64(outputs[j],n),static_cast<uint32_t>(vertex),messages[j]});
        }
    }
    std::sort(samples.begin(),samples.end());
    Layer result;
    auto& stats=result.layer;
    stats.oracle_queries=total; // classical queries: each GOST compression counts once
    stats.simulator_evaluations=total;
    // At a given hash value retain one representative from each vertex.
    std::unordered_set<uint64_t> emitted;
    for(size_t start=0;start<samples.size();) {
        size_t stop=start+1;
        while(stop<samples.size() && samples[stop].key==samples[start].key) ++stop;
        if(stop-start>1) {
            std::vector<size_t> reps;
            for(size_t j=start;j<stop;++j) {
                bool seen=false;
                for(size_t ix:reps) if(samples[ix].vertex==samples[j].vertex) {seen=true;break;}
                if(!seen) reps.push_back(j);
            }
            for(size_t i=0;i<reps.size();++i) for(size_t j=i+1;j<reps.size();++j) {
                const auto& a=samples[reps[i]];
                const auto& b=samples[reps[j]];
                const uint64_t key=uint64_t(a.vertex)*hex_states.size()+b.vertex;
                if(emitted.insert(key).second) {
                    QuantumEdge edge;
                    edge.left=a.vertex;edge.right=b.vertex;
                    edge.left_block=a.block;edge.right_block=b.block;
                    edge.common=reduced_state_from_hex(
                        [&]() { char t[17]={}; static const char digits[]="0123456789abcdef";
                          uint64_t val=a.key;
                          for(int h=(n/4)-1;h>=0;--h) { t[h]=digits[val&15];val>>=4; }
                          return std::string(t,n/4); }(),n);
                    stats.edges.push_back(edge);
                }
            }
        }
        start=stop;
    }
    result.searches=1;
    return result;
}

struct Link {
    bool found=false;
    State block{};
    State target{};
    uint64_t queries=0;
};
inline Link find_link(const std::string& prefix_hex,
                      const std::vector<std::string>& targets_hex,
                      uint64_t max_candidates, uint64_t N,int n,int rounds,
                      uint64_t seed,int threads,int sigma_bits,
                      uint64_t current_sigma,uint64_t target_sigma) {
    if(n>64 || !max_candidates) throw std::runtime_error("Classical link: invalid n or range");
    const uint64_t low=required_sigma_low64(current_sigma,target_sigma,sigma_bits);
    herding_link::QuantumTargets targets(targets_hex,n);
    const auto ctx=make_context(reduced_state_from_hex(prefix_hex,n),N,rounds);
    const size_t chunk_size=4096;
    WorkerPool pool(threads,chunk_size,128);
    std::vector<State> messages,outputs;
    Link result;
    for(uint64_t offset=0;offset<max_candidates;offset+=chunk_size) {
        const size_t count=static_cast<size_t>(std::min<uint64_t>(chunk_size,max_candidates-offset));
        messages.resize(count);
        for(size_t j=0;j<count;++j)messages[j]=message(offset+j,seed,sigma_bits,low);
        quantum_diamond::evaluate_message_space_into(ctx,messages,outputs,threads,&pool);
        result.queries+=count;
        for(size_t j=0;j<count;++j) if(targets.contains(outputs[j])) {
            result.found=true;
            result.block=messages[j];
            result.target=outputs[j];
            return result;
        }
    }
    return result;
}
} //namespace classical_herding_cli
