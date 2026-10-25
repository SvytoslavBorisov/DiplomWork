#define main gost_core_command_main
#include "gost_core.cpp"
#undef main
using grover_analytic::simulate_fixed_measurement;
static void require(bool valid,const char* message){if(!valid)throw std::runtime_error(message);}
int main(){
  try{
    std::mt19937_64 rng(731);
    Xoshiro256ss reference_rng(std::array<uint64_t,4>{1,2,3,4});
    require(reference_rng()==11520 && reference_rng()==0 && reference_rng()==1509978240ULL,"xoshiro published-state sequence");
    Xoshiro256ss base(731),same(731),jumped(731);jumped.jump();
    for(int i=0;i<1000;++i){const auto value=base();require(value==same(),"xoshiro seed reproduction");require(value!=jumped(),"xoshiro jumped stream separation");}
    for(int n:{1,32,64,65}){
      requested_qram="generic";QuantumQram generic(1000,n);
      requested_qram="u64";QuantumQram optimized(1000,n);
      require(optimized.uses_u64()==(n<=64),"qRAM fallback selection");
      std::vector<State> outputs;
      for(size_t i=0;i<1000;++i){State h=random_state(rng);if(i%3==0 && !outputs.empty())h=outputs.back();outputs.push_back(h);QuantumTableEntry e{i%7,random_state(rng)};generic.insert(h,e);optimized.insert(h,e);}
      for(const auto& h:outputs){auto a=generic.find(h),b=optimized.find(h);require(a && b && a->size()==b->size(),"qRAM size");for(size_t i=0;i<a->size();++i)require((*a)[i].vertex==(*b)[i].vertex && (*a)[i].block==(*b)[i].block,"qRAM insertion order / duplicate partners");}
      for(int i=0;i<1000;++i){auto h=random_state(rng);auto a=generic.find(h),b=optimized.find(h);require(bool(a)==bool(b),"qRAM miss");}
    }
    QuantumLayerWorkspace workspace;
    workspace.resize_messages(256);workspace.prepare_outputs(256);
    const auto capacity=workspace.messages.capacity(),out_capacity=workspace.outputs.capacity();
    workspace.resize_messages(3);workspace.prepare_outputs(3);
    require(workspace.messages.capacity()==capacity && workspace.outputs.capacity()==out_capacity,"workspace capacity shrink");
    auto context=make_context(State{},512,12);
    for(auto& message:workspace.messages)message=random_state(rng);
    evaluate_message_space_into(context,workspace.messages,workspace.outputs,4);
    for(size_t i=0;i<workspace.messages.size();++i)require(workspace.outputs[i]==compress_with_context(workspace.messages[i],context),"workspace stale output");
    workspace.resize_messages(129);
    for(auto& message:workspace.messages)message=random_state(rng);
    evaluate_message_space_into(context,workspace.messages,workspace.outputs,2);
    for(size_t i=0;i<workspace.messages.size();++i)require(workspace.outputs[i]==compress_with_context(workspace.messages[i],context),"workspace stale larger output");
    for(int threads:{1,2,4}){
      WorkerPool pool(threads,4096,1);const auto starts=pool.worker_start_count();
      std::vector<uint64_t> slots(4096);
      for(int repeat=0;repeat<100;++repeat){
        pool.run(slots.size(),1,[&](WorkRange range){if(range.begin)std::this_thread::yield();for(uint64_t i=range.begin;i<range.end;++i)slots[static_cast<size_t>(i)]=mix64(i+repeat);});
        for(size_t i=0;i<slots.size();++i)require(slots[i]==mix64(i+repeat),"pool disjoint ranges / scheduling");
      }
      require(pool.worker_start_count()==starts,"pool worker recreation");
      bool propagated=false;
      try{pool.run(4096,1,[&](WorkRange range){if(range.end==4096)throw std::runtime_error("worker fixture");});}catch(const std::runtime_error&){propagated=true;}
      require(propagated,"worker exception propagation");
      pool.run(4096,1,[](WorkRange){});
    }
    // Сравнивает измерения, состояние генератора и равномерность выбора помеченных элементов.
    for(const std::vector<uint8_t> marked: {std::vector<uint8_t>(16,0),std::vector<uint8_t>{1,0,1,0,0,0,0,1,0,0,0,0,0,1,0,0}}){
      std::array<uint64_t,16> frequencies{};
      const uint64_t count=std::count(marked.begin(),marked.end(),uint8_t{1});
      for(uint64_t seed=0;seed<20000;++seed){
        std::mt19937_64 old_rng(seed),new_rng(seed);uint64_t old_queries=0,new_queries=0;
        auto old=simulate_fixed_measurement(marked,old_rng,old_queries);
        auto current=simulate_fixed_measurement(marked.size(),count,[&](size_t i){return marked[i]!=0;},new_rng,new_queries);
        require(old==current && old_queries==new_queries && old_rng()==new_rng(),"fixed measurement/RNG compatibility");
        if(current<marked.size())++frequencies[current];
      }
      if(count){
        uint64_t successes=0;for(auto value:frequencies)successes+=value;
        const double expected=double(successes)/count;
        const double tolerance=6*std::sqrt(expected*(1.0-1.0/count))+1;
        for(size_t i=0;i<marked.size();++i)if(marked[i])require(std::abs(double(frequencies[i])-expected)<tolerance,"conditional marked choice uniformity");
      }
    }
    std::cout<<"OK OPTIMIZATION_NATIVE_TESTS_PASS\n";return 0;
  }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
