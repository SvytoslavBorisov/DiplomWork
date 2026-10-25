#include "bbht_adaptive.hpp"
#include "quantum_collision_search.hpp"
#include "herding_search.hpp"
#include <iostream>

// Проверяет политику попыток независимо от включения assert в сборке Release.
static void require(bool value, const char* message) {
    if (!value) throw std::runtime_error(message);
}
static void counters(const bbht_adaptive::Result& result) {
    require(result.oracle_queries==result.phase_oracle_queries+result.verification_queries,"Нарушена сумма запросов.");
    require(result.attempts==result.verification_queries,"Потеряна проверка результата.");
    require(result.failures+uint64_t(result.found)==result.attempts,"Потеряна неудачная попытка.");
    require(result.attempts<=result.effective_max_attempts,"Превышен эффективный лимит.");
}
int main() {
    try {
        using bbht_adaptive::effective_max_attempts;
        require(effective_max_attempts(1,1.2)==8,"Неверный лимит S=1.");
        require(effective_max_attempts(56,1.2)==20,"Неверный лимит S=56.");
        require(effective_max_attempts(2048,1.2)==29,"Неверный лимит S=2048.");
        require(effective_max_attempts(UINT64_MAX,1.2)<=128,"Переполнение большого S.");
        require(effective_max_attempts(UINT64_MAX,std::nextafter(1.0,2.0),UINT64_MAX)>128,"Потерян большой предел.");
        require(effective_max_attempts(56,1.2,3)==3,"Не применён пользовательский предел.");
        require(effective_max_attempts(2048,1.1)>effective_max_attempts(2048,1.2),"Не учтён growth.");
        for(double growth:{1.0,0.0,4.0/3.0,std::numeric_limits<double>::infinity()}) {
            bool refused=false;
            try { effective_max_attempts(56,growth); } catch(const std::runtime_error&) { refused=true; }
            require(refused,"Принят недопустимый рост.");
        }
        bool refused=false;
        try { effective_max_attempts(0,1.2); } catch(const std::runtime_error&) { refused=true; }
        require(refused,"Принято пустое пространство.");
        for(size_t R:{size_t{0},size_t{1},size_t{4}}) {
            std::vector<uint8_t> marked(56);
            for(size_t i=0;i<R;++i)marked[3+i*7]=1;
            uint64_t successes=0;
            for(uint64_t seed=0;seed<200;++seed) {
                std::mt19937_64 rng(seed);
                uint64_t checks=0;
                const auto fixed=bbht_adaptive::fixed_single(marked,rng,[&](size_t i){++checks;return marked[i]!=0;});
                counters(fixed);
                require(fixed.attempts==1 && checks==1,"Фиксированный Гровер повторил измерение.");
                require(fixed.phase_oracle_queries==grover_analytic::optimal_grover_iterations(56,1),"Использовано знание R.");
                require(fixed.found==(marked[fixed.measured_index]!=0),"Ложный успех фиксированного поиска.");
                rng.seed(seed);
                checks=0;
                const auto adaptive=bbht_adaptive::search(marked,rng,[&](size_t i){++checks;return marked[i]!=0;});
                counters(adaptive);
                require(checks==adaptive.attempts,"Проверка не соответствует числу измерений.");
                if(!R) require(adaptive.attempts==20 && !adaptive.found,"Получено бесплатное знание об R=0.");
                successes+=adaptive.found;
            }
            if(R) require(successes>180,"Существенно нарушена вероятность успеха BBHT.");
            else require(!successes,"Обнаружен ложный успех при R=0.");
        }
        std::vector<std::string> states={"00","40","80","c0"};
        bbht_adaptive::Options options;
        options.max_attempts=128;
        options.max_oracle_queries=1;
        options.dense_max_states=16;
        options.growth=1.3;
        const auto standard=quantum_diamond::build_quantum_layer(states,32,129,2,1024,8,12,51,1,4,3,7);
        const auto experimental=quantum_diamond_bbht::build_layer(states,32,129,2,1024,8,12,51,1,4,3,7,options,true);
        require(standard.oracle_queries==experimental.layer.oracle_queries &&
                standard.simulator_evaluations==experimental.layer.simulator_evaluations,"Маршруты слоя используют разные запросы.");
        require(standard.edges.size()==experimental.layer.edges.size(),"Маршруты слоя выбрали разные коллизии.");
        for(size_t i=0;i<standard.edges.size();++i) {
            const auto& a=standard.edges[i];const auto& b=experimental.layer.edges[i];
            require(a.left==b.left && a.right==b.right && a.left_block==b.left_block &&
                    a.right_block==b.right_block && a.common==b.common,"Нарушена повторяемость общего фиксированного поиска.");
        }
        for(const auto& search:experimental.layer.search_diagnostics) require(search.attempts==1,"Унаследован предел BBHT.");
        const auto link=herding_link::find_quantum_link("00",states,129,512,8,12,51,1,4,3,7);
        const auto control=herding_link_bbht::find("00",states,129,512,8,12,51,1,4,3,7,options,true);
        require(link.oracle_queries==control.link.oracle_queries && link.block==control.link.block &&
                link.target==control.link.target && control.search.attempts==1,"Маршруты linking используют разные политики.");
        std::cout << "PASS: fixed_single, bbht_auto, limits, zero solutions, counters, common routes\n";
        return 0;
    } catch(const std::exception& error) { std::cerr << error.what() << '\n'; return 1; }
}
