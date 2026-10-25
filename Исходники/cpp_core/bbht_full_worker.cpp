// Standalone command-line worker for the full-diamond BBHT experiment.
// Does not alter the standard attack and does not link to GUI code.
#include <algorithm>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <limits>
#include <map>
#include <stdexcept>
#include <string>
#include <vector>
#include "herding_search.hpp"
#include "quantum_collision_search.hpp"
#include "classical_herding_cli.hpp"

namespace {
using Args = std::map<std::string, std::string>;
std::string get(const Args& args, const std::string& key, const std::string& fallback="") {
    const auto it=args.find(key);
    return it==args.end()?fallback:it->second;
}
uint64_t number(const Args& args, const std::string& key, uint64_t default_value=0) {
    const auto it=args.find(key);
    if(it==args.end()) return default_value;
    if(it->second.empty() || it->second[0]=='-') throw std::runtime_error("Negative or empty --"+key);
    size_t count=0;
    const uint64_t value=std::stoull(it->second,&count);
    if(count!=it->second.size()) throw std::runtime_error("Invalid --"+key);
    return value;
}
std::string full_hex(const gost_reduced_model::State& state) {
    static constexpr char hexdigits[]="0123456789abcdef";
    std::string output(128,'0');
    for(size_t i=0;i<8;++i) {
        const uint64_t word=state[i];
        for(size_t j=0;j<16;++j)
            output[i*16+j]=hexdigits[(word >> (60-4*j)) & 0xfu];
    }
    return output;
}
gost_reduced_model::State parse_block(const std::string& hex) {
    if(hex.size()!=128 || hex.find_first_not_of("0123456789abcdefABCDEF")!=std::string::npos)
        throw std::runtime_error("Malformed 512-bit message block");
    gost_reduced_model::State block{};
    for(size_t i=0;i<8;++i)
        for(size_t j=0;j<16;++j)
            block[i]=(block[i]<<4)|gost_reduced_model::hex_value(hex[16*i+j]);
    return block;
}
std::vector<std::string> read_states(const std::string& path, int n) {
    std::ifstream stream(path);
    if(!stream) throw std::runtime_error("Cannot open states file: "+path);
    std::vector<std::string> states;
    std::string state;
    while(stream>>state) {
        // Reject malformed states without truncating values silently.
        if(state.size()!=static_cast<size_t>(n/4) || state.find_first_not_of("0123456789abcdefABCDEF")!=std::string::npos)
            throw std::runtime_error("Invalid n-bit state in input file");
        states.push_back(state);
    }
    return states;
}
void print_stats(uint64_t oracle, uint64_t phase, uint64_t verification,
                 uint64_t gost, uint64_t qram, uint64_t marked,
                 uint64_t attempts, uint64_t failures, uint64_t success_searches,
                 uint64_t total_searches, uint64_t exhausted,
                 uint64_t edges, uint64_t iterations,
                 uint64_t elements, double seconds) {
    std::cout << "STATS " << oracle << ' ' << phase << ' ' << verification << ' '
              << gost << ' ' << qram << ' ' << marked << ' ' << attempts << ' '
              << failures << ' ' << success_searches << ' ' << total_searches << ' '
              << exhausted << ' ' << edges << ' ' << iterations << ' '
              << elements << ' ' << seconds << '\n';
}
}

int main(int argc,char** argv) {
    try {
        Args args;
        for(int i=1;i<argc;++i) {
            if(std::string(argv[i])=="--help") {
                std::cout<<"bbht_full_worker --task layer|link --states-file PATH "
                           "--prefix HEX [--r BITS] --n BITS --s BITS --N BITS "
                           "--current-sigma VALUE --target-sigma VALUE --L SIZE --S SIZE "
                           "--seed VALUE --method bbht|fixed_repeated|classical "
                           "--max-attempts COUNT --max-queries COUNT --threads COUNT --rounds COUNT\n";
                return 0;
            }
            const std::string key=argv[i];
            if(key.rfind("--",0)!=0 || i+1==argc)throw std::runtime_error("Expected --key value");
            args[key.substr(2)]=argv[++i];
        }
        const std::string task=get(args,"task");
        const auto raw_method=get(args,"method","bbht");
        const std::string method=(raw_method=="fixed_repeated" ? "grover_fixed" :
                                  raw_method=="grover_bbht" ? "bbht" : raw_method);
        const int n=static_cast<int>(number(args,"n",12));
        const int s=static_cast<int>(number(args,"s",0));
        const int rounds=static_cast<int>(number(args,"rounds",12));
        const int threads=static_cast<int>(number(args,"threads",2));
        const uint64_t N=number(args,"N",1024);
        const uint64_t L=number(args,"L",32);
        const uint64_t S=number(args,"S",1024);
        const uint64_t seed=number(args,"seed",42);
        const uint64_t current_sigma=number(args,"current-sigma",0);
        const uint64_t target_sigma=number(args,"target-sigma",0);
        if((task!="layer" && task!="link" && task!="replay") ||
           (method!="bbht" && method!="grover_fixed" && method!="classical") ||
           n<4 || n>512 || n%4 || s<0 || s>64 || rounds<1 || rounds>12 ||
           threads<1 || !S || !L || N%512 ||
           !args.count("states-file"))
            throw std::runtime_error("Invalid configuration");
        bbht_adaptive::Options options;
        options.growth=std::stod(get(args,"growth","1.2"));
        options.max_attempts=number(args,"max-attempts",128);
        options.max_oracle_queries=number(args,"max-queries",100000);
        options.dense_max_states=number(args,"dense-max-S",8192);
        options.max_stage_seconds=static_cast<double>(number(args,"stage-timeout",0));
        if(method=="bbht") bbht_adaptive::effective_max_attempts(S,options.growth,options.max_attempts);
        // Diagnostic emitted only on worker failure: makes it possible to
        // distinguish dense and exact-symmetric execution in Windows logs.
        const std::string backend = (method == "classical") ? "classical" :
            (S <= options.dense_max_states ? "dense-no-deadline" : "symmetric");
        std::string worker_context = " task=" + task + " n=" + std::to_string(n) +
            " S=" + std::to_string(S) + " dense_max_S=" +
            std::to_string(options.dense_max_states) + " backend=" + backend;

        if(task != "replay") std::cerr << "BBHT worker setup:" << worker_context << '\n';
        if(task=="replay") {
            std::ifstream input(get(args,"states-file"));
            if(!input) throw std::runtime_error("Cannot open replay blocks");
            gost_reduced_model::State state{};
            uint64_t sigma=0, counter=0;
            std::string block_hex;
            while(input>>block_hex) {
                const auto block=parse_block(block_hex);
                state=gost_reduced_model::compress_with_context(
                    block,gost_reduced_model::make_context(state,counter,rounds));
                // Explicitly embed the truncated state before every transition.
                state=gost_reduced_model::reduced_state_from_hex(
                    gost_reduced_model::reduced_state_to_hex(state,n),n);
                sigma=(sigma+block[7])&gost_reduced_model::sigma_mask64(s);
                if(counter>std::numeric_limits<uint64_t>::max()-512)
                    throw std::runtime_error("N overflow");
                counter+=512;
            }
            std::cout<<"REPLAY "<<gost_reduced_model::reduced_state_to_hex(state,n)
                     <<' '<<sigma<<' '<<counter<<'\n';
            return 0;
        }
        const auto states=read_states(get(args,"states-file"),n);
        const bool fixed=method=="grover_fixed";
        if(task=="layer") {
            const int r=static_cast<int>(number(args,"r",0));
            if(r<1 || r>16 || static_cast<uint64_t>(states.size())!=(uint64_t{1}<<r))
                throw std::runtime_error("Invalid number of vertices for the given level");
            if(method=="classical") {
                const auto result=classical_herding_cli::build_layer(
                    states,L,N,n,rounds,seed,threads,s,current_sigma,target_sigma);
                const auto& layer=result.layer;
                print_stats(layer.oracle_queries,0,0,layer.simulator_evaluations,0,0,
                            0,0,0,result.searches,0,layer.edges.size(),0,0,0.0);
                for(const auto& edge:layer.edges)
                    std::cout<<"EDGE "<<edge.left<<' '<<edge.right<<' '
                             <<full_hex(edge.left_block)<<' '<<full_hex(edge.right_block)<<' '
                             <<gost_reduced_model::reduced_state_to_hex(edge.common,n)<<'\n';
                return 0;
            }
            const auto result=quantum_diamond_bbht::build_layer(
                states,L,S,r,N,n,rounds,seed,threads,s,current_sigma,target_sigma,options,fixed);
            const auto& layer=result.layer;
            print_stats(layer.oracle_queries,result.phase_oracle_queries,result.verification_queries,
                        layer.simulator_evaluations,layer.qram_entries,layer.marked_elements,
                        layer.grover_attempts,result.failures,result.successful_searches,
                        result.total_searches,result.exhausted_searches,layer.edges.size(),
                        layer.statevector_iterations,layer.statevector_elements_processed,
                        layer.statevector_seconds);
            bbht_adaptive::write_diagnostics(std::cout, layer.search_diagnostics);
            std::cout << '\n';
            for(const auto& edge:layer.edges) {
                std::cout<<"EDGE "<<edge.left<<' '<<edge.right<<' '
                         <<full_hex(edge.left_block)<<' '
                         <<full_hex(edge.right_block)<<' '
                         <<gost_reduced_model::reduced_state_to_hex(edge.common,n)<<'\n';
            }
        } else {
            if(states.empty() || get(args,"prefix").empty())
                throw std::runtime_error("Link task needs targets and prefix");
            if(method=="classical") {
                const auto result=classical_herding_cli::find_link(
                    get(args,"prefix"),states,S,N,n,rounds,seed,threads,s,
                    current_sigma,target_sigma);
                print_stats(result.queries,0,0,result.queries,0,0,0,0,result.found?1:0,
                            1,result.found?0:1,0,0,0,0.0);
                if(result.found)
                    std::cout<<"LINK "<<full_hex(result.block)<<' '
                             <<gost_reduced_model::reduced_state_to_hex(result.target,n)<<'\n';
                else std::cout<<"NO_LINK\n";
                return 0;
            }
            const auto result=herding_link_bbht::find(
                get(args,"prefix"),states,S,N,n,rounds,seed,threads,s,
                current_sigma,target_sigma,options,fixed);
            const auto& sr=result.search;
            print_stats(sr.oracle_queries,sr.phase_oracle_queries,sr.verification_queries,
                        result.link.simulator_evaluations,0,sr.marked_count_diagnostic,
                        sr.attempts,sr.failures,sr.found?1:0,1,sr.exhausted?1:0,0,
                        sr.statevector_iterations,sr.statevector_elements_processed,
                        sr.statevector_seconds);
            bbht_adaptive::write_diagnostics(std::cout, result.link.search_diagnostics);
            std::cout << '\n';
            if(result.link.found)
                std::cout<<"LINK "<<full_hex(result.link.block)<<' '
                         <<gost_reduced_model::reduced_state_to_hex(result.link.target,n)<<'\n';
            else std::cout<<"NO_LINK\n";
        }
        return 0;
    } catch(const std::exception& error) {
        std::cerr<<"BBHT full worker error: "<<error.what()<<'\n';
        return 2;
    }
}
