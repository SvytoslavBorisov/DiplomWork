#include <algorithm>
#include <cstdint>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <map>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>
#include "herding_link_bbht.hpp"
#include "quantum_diamond_bbht.hpp"

// Предоставляет автономный эксперимент без изменения существующего исполняемого ядра.
namespace {

std::string arg(const std::map<std::string, std::string>& a, const std::string& key, const std::string& default_value) {
    const auto it = a.find(key);
    return it == a.end() ? default_value : it->second;
}
uint64_t integer(const std::map<std::string, std::string>& a, const std::string& key, uint64_t default_value) {
    const auto it = a.find(key);
    if (it == a.end()) return default_value;
    if (it->second.empty() || it->second[0] == '-')
        throw std::runtime_error("Недопустимое отрицательное значение --" + key);
    size_t consumed = 0;
    const auto value = std::stoull(it->second, &consumed);
    if (consumed != it->second.size()) throw std::runtime_error("Некорректный параметр --" + key);
    return value;
}
void emit(const std::string& path, const std::string& line, bool header = false) {
    if (path.empty()) {
        if (header) std::cout << line << '\n';
        else std::cout << line << '\n';
        return;
    }
    bool needs_header = true;
    {
        std::ifstream old(path, std::ios::binary | std::ios::ate);
        needs_header = !old || old.tellg() == 0;
    }
    std::ofstream out(path, std::ios::app);
    if (!out) throw std::runtime_error("Невозможно записать CSV: " + path);
    if (header) {
        if (needs_header) out << line << '\n';
    } else out << line << '\n';
}

const char* search_csv_header =
    "experiment,method,n,k,s,N,rounds,seed,L,S,vertex,repetition,marked_count,"
    "found,exhausted,oracle_queries,phase_oracle_queries,verification_queries,"
    "attempts,failed_attempts,search_protocol,attempt_policy,growth,effective_max_attempts,stop_reason";

const char* csv_header =
    "experiment,method,n,k,s,N,rounds,seed,L,S,targets,complete,exhausted,"
    "oracle_queries,phase_oracle_queries,verification_queries,"
    "classical_gost_evaluations,qram_entries,marked_count,attempts,failed_attempts,"
    "successful_searches,total_searches,edges,statevector_operations,statevector_seconds,"
    "search_protocol,attempt_policy,growth,effective_max_attempts,stop_reason";

void print_record(const std::string& csv, const std::string& experiment, const std::string& method,
                  int n, int k, int s, uint64_t N, int rounds, uint64_t seed, uint64_t L,
                  uint64_t S, uint64_t targets, bool complete, bool exhausted,
                  uint64_t oracle, uint64_t phase, uint64_t verification, uint64_t physical,
                  uint64_t qram, uint64_t marked, uint64_t attempts, uint64_t failed,
                  uint64_t successful, uint64_t total, uint64_t edges, uint64_t operations, double seconds,
                  const bbht_adaptive::Options& options, const char* reason) {
    std::ostringstream out;
    out << experiment << ',' << method << ',' << n << ',' << k << ',' << s << ',' << N << ','
        << rounds << ',' << seed << ',' << L << ',' << S << ',' << targets << ','
        << (complete ? 1 : 0) << ',' << (exhausted ? 1 : 0) << ',' << oracle << ','
        << phase << ',' << verification << ',' << physical << ',' << qram << ','
        << marked << ',' << attempts << ',' << failed << ',' << successful << ',' << total
        << ',' << edges << ',' << operations << ',' << std::setprecision(17) << seconds
        << ',' << bbht_adaptive::search_protocol << ',' << (method=="grover_fixed" ? "fixed_single" : "bbht_auto")
        << ',' << options.growth << ',' << (method=="grover_fixed" ? 1 : bbht_adaptive::effective_max_attempts(S,options.growth,options.max_attempts))
        << ',' << reason;
    emit(csv, out.str());
}

void run_trial(const std::string& experiment, const std::string& method,
               int n, int k, int s, uint64_t N, int rounds, uint64_t seed,
               uint64_t L, uint64_t S, int threads, const bbht_adaptive::Options& options,
               const std::string& csv, const std::string& search_csv) {
    const bool fixed = method == "grover_fixed";
    const uint64_t current_sigma = s ? 1 : 0;
    const uint64_t target_sigma = s ? 3 : 0;
    if (experiment == "linking") {
        State prefix_state{};
        prefix_state[0] = mix64(seed ^ 0xabcaULL);
        const std::string prefix = gost_reduced_model::reduced_state_to_hex(prefix_state, n);
        std::vector<std::string> targets;
        targets.reserve(uint64_t{1} << k);
        for (uint64_t i = 0; i < (uint64_t{1} << k); ++i) {
            State state{};
            state[0] = mix64(seed ^ (i + 0x7ecaULL));
            targets.push_back(gost_reduced_model::reduced_state_to_hex(state, n));
        }
        const auto r = herding_link_bbht::find(prefix, targets, S, N, n, rounds,
                                                seed, threads, s, current_sigma, target_sigma,
                                                options, fixed);
        if (r.link.found) {
            const auto ctx = gost_reduced_model::make_context(
                gost_reduced_model::reduced_state_from_hex(prefix, n), N, rounds);
            const auto output = gost_reduced_model::compress_with_context(r.link.block, ctx);
            if (gost_reduced_model::reduced_state_to_hex(output, n) !=
                gost_reduced_model::reduced_state_to_hex(r.link.target, n))
                throw std::runtime_error("Проверка связывающего блока не прошла.");
        }
        print_record(csv, experiment, method, n, k, s, N, rounds, seed, 0, S, targets.size(),
                     r.link.found, r.search.exhausted, r.search.oracle_queries,
                     r.search.phase_oracle_queries, r.search.verification_queries,
                     r.link.simulator_evaluations, 0, r.search.marked_count_diagnostic,
                     r.search.attempts, r.search.failures, r.link.found ? 1 : 0, 1, 0,
                     r.search.statevector_elements_processed, r.search.statevector_seconds, options, r.search.stop_reason);
    } else if (experiment == "diamond_layer") {
        std::vector<std::string> states;
        states.reserve(uint64_t{1} << k);
        for (uint64_t i = 0; i < (uint64_t{1} << k); ++i) {
            State state{};
            state[0] = mix64(seed ^ (i + 0x215fULL));
            states.push_back(gost_reduced_model::reduced_state_to_hex(state, n));
        }
        const auto r = quantum_diamond_bbht::build_layer(states, L, S, k, N, n, rounds,
                                                          seed, threads, s, current_sigma, target_sigma,
                                                          options, fixed);
        for (const auto& edge : r.layer.edges) {
            const auto left = gost_reduced_model::make_context(
                gost_reduced_model::reduced_state_from_hex(states[edge.left], n), N, rounds);
            const auto right = gost_reduced_model::make_context(
                gost_reduced_model::reduced_state_from_hex(states[edge.right], n), N, rounds);
            if (gost_reduced_model::reduced_state_to_hex(
                    gost_reduced_model::compress_with_context(edge.left_block, left), n) !=
                    gost_reduced_model::reduced_state_to_hex(edge.common, n) ||
                gost_reduced_model::reduced_state_to_hex(
                    gost_reduced_model::compress_with_context(edge.right_block, right), n) !=
                    gost_reduced_model::reduced_state_to_hex(edge.common, n))
                throw std::runtime_error("Проверка коллизии алмазной структуры не прошла.");
        }
        print_record(csv, experiment, method, n, k, s, N, rounds, seed, L, S, states.size(),
                     r.successful_searches == r.total_searches, r.exhausted_searches > 0,
                     r.layer.oracle_queries, r.phase_oracle_queries, r.verification_queries,
                     r.layer.simulator_evaluations, r.layer.qram_entries, r.layer.marked_elements,
                     r.layer.grover_attempts, r.failures, r.successful_searches, r.total_searches,
                     r.layer.edges.size(), r.layer.statevector_elements_processed,
                     r.layer.statevector_seconds, options, r.exhausted_searches ? "search_failures" : "found");
        if (!search_csv.empty()) {
            for (const auto& observation : r.searches) {
                std::ostringstream row;
                row << experiment << ',' << method << ',' << n << ',' << k << ',' << s
                    << ',' << N << ',' << rounds << ',' << seed << ',' << L << ',' << S
                    << ',' << observation.vertex << ',' << observation.repetition
                    << ',' << observation.marked_count << ',' << (observation.found ? 1 : 0)
                    << ',' << (observation.exhausted ? 1 : 0)
                    << ',' << observation.oracle_queries << ',' << observation.phase_oracle_queries
                    << ',' << observation.verification_queries << ',' << observation.attempts
                    << ',' << observation.failed_attempts << ',' << bbht_adaptive::search_protocol
                    << ',' << observation.attempt_policy << ',' << observation.growth
                    << ',' << observation.effective_max_attempts << ',' << observation.stop_reason;
                emit(search_csv, row.str());
            }
        }
    } else throw std::runtime_error("Неизвестный режим: " + experiment);
}

} // namespace

int main(int argc, char** argv) {
    try {
        std::map<std::string, std::string> args;
        for (int i = 1; i < argc; ++i) {
            const std::string item(argv[i]);
            if (item == "--help") {
                std::cout << "BBHT experiment: --experiment linking|diamond_layer --method both|bbht|fixed_repeated "
                    "--n 12 --k 3 --s 0 --N 512 --L 32 --S 1024 --trials 10 --seed 42 "
                    "--rounds 12 --threads 2 --max-attempts 128 --max-queries 100000 "
                    "--csv results.csv [--search-csv searches.csv] [--append 1]\n";
                return 0;
            }
            if (item.rfind("--", 0) != 0 || i + 1 == argc)
                throw std::runtime_error("Ожидается аргумент вида --ключ значение.");
            args[item.substr(2)] = argv[++i];
        }
        const auto experiment = arg(args, "experiment", "linking");
        const auto raw_method = arg(args, "method", "both");
        const auto method = raw_method == "fixed_repeated" ? "grover_fixed" : raw_method;
        const int n = static_cast<int>(integer(args, "n", 12));
        const int k = static_cast<int>(integer(args, "k", 3));
        const int s = static_cast<int>(integer(args, "s", 0));
        const int rounds = static_cast<int>(integer(args, "rounds", 12));
        const int threads = static_cast<int>(integer(args, "threads", 2));
        const uint64_t N = integer(args, "N", 512);
        const uint64_t L = integer(args, "L", 32);
        const uint64_t S = integer(args, "S", 1024);
        const uint64_t trials = integer(args, "trials", 10);
        const uint64_t seed = integer(args, "seed", 42);
        const std::string csv = arg(args, "csv", "");
        const std::string search_csv = arg(args, "search-csv", "");
        const bool append = integer(args, "append", 0) != 0;
        bbht_adaptive::Options options;
        options.growth = std::stod(arg(args, "growth", "1.2"));
        options.max_attempts = integer(args, "max-attempts", 128);
        options.max_oracle_queries = integer(args, "max-queries", 100000);
        if (n < 1 || n > 512 || k < 1 || k > 16 || s < 0 || s > 64 ||
            rounds < 1 || rounds > 12 || !S || !L || !trials || threads < 1 ||
            (method != "both" && method != "bbht" && method != "grover_fixed"))
            throw std::runtime_error("Параметры эксперимента некорректны.");
        if(method!="grover_fixed") bbht_adaptive::effective_max_attempts(S,options.growth,options.max_attempts);
        if (!csv.empty() && csv == search_csv)
            throw std::runtime_error("Итоговый CSV и журнал поисков должны иметь разные пути.");
        if (append) {
            for (const auto& item : {std::make_pair(csv,csv_header), std::make_pair(search_csv,search_csv_header)}) {
                if(item.first.empty()) continue;
                std::ifstream previous(item.first);
                std::string header;
                if(std::getline(previous,header) && !header.empty() && header!=item.second)
                    throw std::runtime_error("CSV использует прежний протокол; выберите новый файл отчёта.");
            }
        } else {
            for (const auto& path : {csv, search_csv}) {
                if (path.empty()) continue;
                std::ifstream previous(path, std::ios::binary | std::ios::ate);
                if (previous && previous.tellg() > 0)
                    throw std::runtime_error("CSV уже существует; выберите новый файл или укажите --append 1.");
            }
        }
        emit(csv, csv_header, true);
        if (!search_csv.empty() && experiment == "diamond_layer")
            emit(search_csv, search_csv_header, true);
        for (uint64_t trial = 0; trial < trials; ++trial) {
            const uint64_t trial_seed = seed + trial * 0x9e3779b97f4a7c15ULL;
            if (method == "both" || method == "grover_fixed")
                run_trial(experiment, "grover_fixed", n, k, s, N, rounds, trial_seed,
                          L, S, threads, options, csv, search_csv);
            if (method == "both" || method == "bbht")
                run_trial(experiment, "bbht", n, k, s, N, rounds, trial_seed,
                          L, S, threads, options, csv, search_csv);
        }
        if (!csv.empty()) std::cout << "Эксперимент завершён: " << csv << '\n';
    } catch (const std::exception& ex) {
        std::cerr << "ERROR: " << ex.what() << '\n';
        return 1;
    }
    return 0;
}
