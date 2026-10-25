#pragma once
#include <condition_variable>
#include <mutex>

// Синхронный пул распределяет непересекающиеся диапазоны между потоками для одного вызывающего координатора.

class WorkerPool {
public:
    WorkerPool(int requested,uint64_t scope_size,uint64_t grain)
      : count_(workers_for_limit(requested,scope_size,grain)),errors_(static_cast<size_t>(count_)) {
        try {
            for(int tid=1;tid<count_;++tid)workers_.emplace_back([this,tid]{worker(tid);});
        }catch(...){shutdown();throw;}
    }
    ~WorkerPool(){shutdown();}
    WorkerPool(const WorkerPool&)=delete;
    WorkerPool& operator=(const WorkerPool&)=delete;
    size_t worker_start_count()const{return workers_.size();}

    template<class Work> void run(uint64_t total,uint64_t grain,Work work) {
        const int active=static_cast<int>(std::min<uint64_t>(count_,std::max<uint64_t>(1,total/grain)));
        if(active==1){work({0,total});return;}
        {
            std::lock_guard<std::mutex> lock(mutex_);
            if(running_)throw std::logic_error("WorkerPool requires a single caller");
            running_=true;total_=total;active_=active;completed_=0;
            for(auto& error:errors_)error=nullptr;
            job_=work;++generation_;
        }
        ready_.notify_all();
        try{work(work_range_for(total,active,0));}catch(...){errors_[0]=std::current_exception();}
        {
            std::unique_lock<std::mutex> lock(mutex_);
            done_.wait(lock,[&]{return completed_==count_-1;});
            job_={};running_=false;
        }
        for(auto error:errors_)if(error)std::rethrow_exception(error);
    }
private:
    void worker(int tid) {
        uint64_t seen=0;
        for(;;){
            std::unique_lock<std::mutex> lock(mutex_);
            ready_.wait(lock,[&]{return stopping_ || generation_!=seen;});
            if(stopping_)return;
            seen=generation_;const int active=active_;const uint64_t total=total_;
            lock.unlock();
            if(tid<active){
                try{job_(work_range_for(total,active,tid));}
                catch(...){errors_[static_cast<size_t>(tid)]=std::current_exception();}
            }
            lock.lock();++completed_;
            if(completed_==count_-1)done_.notify_one();
        }
    }
    void shutdown()noexcept {
        {std::lock_guard<std::mutex> lock(mutex_);stopping_=true;}
        ready_.notify_all();for(auto& thread:workers_)if(thread.joinable())thread.join();
    }
    int count_,active_=1,completed_=0;
    uint64_t total_=0,generation_=0;
    bool stopping_=false,running_=false;
    std::mutex mutex_;
    std::condition_variable ready_,done_;
    std::vector<std::thread> workers_;
    std::vector<std::exception_ptr> errors_;
    std::function<void(WorkRange)> job_;
};
