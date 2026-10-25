#pragma once
// Python управляет расширением списков и сообщает удалённые рёбра для повторного обнаружения коллизий.

static void run_blackburn_layer(const std::vector<std::string>& states,uint64_t N,int n,int rounds,
    int threads,int s,uint64_t current_sigma,uint64_t target_sigma) {
    if(states.size()<2 || states.size()>std::numeric_limits<uint32_t>::max())throw std::runtime_error("invalid Blackburn vertex count");
    std::unordered_map<ReducedKey,std::vector<QuantumTableEntry>,ReducedKeyHash> buckets;
    std::unordered_set<uint64_t> active_edges;
    const auto edge_key=[&](uint64_t a,uint64_t b){return std::min(a,b)*states.size()+std::max(a,b);};
    WorkerPool pool(threads,uint64_t(nthreads_from(threads))*1024,1024);
    std::cout<<"OK READY\n"<<std::flush;
    std::string command;
    while(std::cin>>command) {
        if(command=="DONE"){std::cout<<"OK DONE\n"<<std::flush;return;}
        if(command=="DROP") {
            uint64_t count;if(!(std::cin>>count))throw std::runtime_error("invalid DROP count");
            for(uint64_t i=0;i<count;++i){uint64_t left,right;if(!(std::cin>>left>>right) || left>=states.size() || right>=states.size())throw std::runtime_error("invalid DROP edge");active_edges.erase(edge_key(left,right));}
            std::cout<<"OK DROP\n"<<std::flush;continue;
        }
        if(command!="GROW")throw std::runtime_error("unknown Blackburn session command");
        uint64_t count,seed;int seeded;
        if(!(std::cin>>count>>seeded>>seed) || count==0)throw std::runtime_error("invalid GROW request");
        has_requested_seed=true;
        requested_seed=seeded?seed:(uint64_t(std::random_device{}())<<32)^std::random_device{}();
        const auto samples=sample_transition_lists(states,count,N,n,rounds,threads,s,current_sigma,target_sigma,&pool);
        std::vector<QuantumEdge> edges;
        for(size_t i=0;i<samples.size();++i) {
            const size_t vertex=i/count;const auto& sample=samples[i];
            auto& entries=buckets[reduced_key_full(sample.output,n)];
            bool has_vertex=false;
            for(const auto& other:entries) {
                if(other.vertex==vertex){has_vertex=true;continue;}
                if(!active_edges.insert(edge_key(other.vertex,vertex)).second)continue;
                edges.push_back({other.vertex,vertex,other.block,sample.block,sample.output});
            }
            if(!has_vertex)entries.push_back({vertex,sample.block});
        }
        std::cout<<"OK "<<samples.size()<<' '<<edges.size();
        for(const auto& edge:edges)std::cout<<' '<<edge.left<<' '<<edge.right<<' '<<state_to_hex(edge.left_block)<<' '<<state_to_hex(edge.right_block)<<' '<<reduced_state_to_hex(edge.common,n)<<' '<<target_sigma;
        std::cout<<'\n'<<std::flush;
    }
}
