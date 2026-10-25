cmake_minimum_required(VERSION 3.16)
project(gost_core LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

if(MSVC)
  add_compile_options(/utf-8)
endif()
add_executable(gost_core gost_core.cpp)
option(GOST_BUILD_STATEVECTOR_TESTS "Build statevector simulation regressions" ON)
if(GOST_BUILD_STATEVECTOR_TESTS)
  enable_testing()
  add_executable(test_grover_statevector test_grover_statevector.cpp test_grover_statevector_odr.cpp)
  add_test(NAME grover_statevector COMMAND test_grover_statevector)
endif()
option(GOST_BUILD_HERDING_LINK_TESTS "Build linking and ODR regressions" OFF)
if(GOST_BUILD_HERDING_LINK_TESTS)
  enable_testing()
  add_executable(test_herding_link test_herding_link.cpp test_herding_link_odr.cpp)
  add_test(NAME herding_link COMMAND test_herding_link)
  if(NOT MSVC)
    target_link_libraries(test_herding_link PRIVATE pthread)
  endif()
endif()
option(GOST_BUILD_QUANTUM_DIAMOND_TESTS "Build quantum layer and ODR regressions" OFF)
if(GOST_BUILD_QUANTUM_DIAMOND_TESTS)
  enable_testing()
  add_executable(test_quantum_diamond
    test_quantum_diamond.cpp
    test_quantum_diamond_odr.cpp
  )
  add_test(NAME quantum_diamond COMMAND test_quantum_diamond)
  if(NOT MSVC)
    target_link_libraries(test_quantum_diamond PRIVATE pthread)
  endif()
endif()
option(GOST_BUILD_GROVER_TESTS "Build standalone analytic Grover and ODR regressions" OFF)
if(GOST_BUILD_GROVER_TESTS)
  enable_testing()
  add_executable(test_grover_analytic
    test_grover_analytic.cpp
    test_grover_analytic_odr.cpp
  )
  add_test(NAME grover_analytic COMMAND test_grover_analytic)
endif()
option(GOST_BUILD_MODEL_TESTS "Build standalone reduced model and ODR regressions" OFF)
if(GOST_BUILD_MODEL_TESTS)
  enable_testing()
  add_executable(test_gost_reduced_model
    test_gost_reduced_model.cpp
    test_gost_reduced_model_odr.cpp
  )
  add_test(NAME gost_reduced_model COMMAND test_gost_reduced_model)
endif()
option(GOST_BUILD_OPTIMIZATION_TESTS "Build native optimization regressions" OFF)
if(GOST_BUILD_OPTIMIZATION_TESTS)
  add_executable(test_optimizations test_optimizations.cpp)
endif()

if(MSVC)
  # Собирает быстрое ядро Release с AVX2 и межмодульной оптимизацией.
  target_compile_options(gost_core PRIVATE
    $<$<CONFIG:Release>:/O2>
    $<$<CONFIG:Release>:/GL>
    $<$<CONFIG:Release>:/arch:AVX2>
    $<$<CONFIG:Release>:/EHsc>
  )
  target_compile_definitions(gost_core PRIVATE
    $<$<CONFIG:Release>:NDEBUG>
    $<$<CONFIG:Release>:_ITERATOR_DEBUG_LEVEL=0>
    $<$<CONFIG:Release>:GOST_FORCE_AVX2=1>
  )
  target_link_options(gost_core PRIVATE
    $<$<CONFIG:Release>:/LTCG>
    $<$<CONFIG:Release>:/OPT:REF>
    $<$<CONFIG:Release>:/OPT:ICF>
  )
else()
  # Собирает проверочное ядро Linux с теми же пакетными операциями AVX2.
  target_compile_options(gost_core PRIVATE -O3 -mavx2 -DNDEBUG -pthread)
  target_compile_definitions(gost_core PRIVATE GOST_FORCE_AVX2=1)
  target_link_libraries(gost_core PRIVATE pthread)
endif()
if(GOST_BUILD_OPTIMIZATION_TESTS)
  get_target_property(core_options gost_core COMPILE_OPTIONS)
  get_target_property(core_definitions gost_core COMPILE_DEFINITIONS)
  get_target_property(core_link_options gost_core LINK_OPTIONS)
  target_compile_options(test_optimizations PRIVATE ${core_options})
  target_compile_definitions(test_optimizations PRIVATE ${core_definitions})
  if(core_link_options)
    target_link_options(test_optimizations PRIVATE ${core_link_options})
  endif()
  if(NOT MSVC)
    target_link_libraries(test_optimizations PRIVATE pthread)
  endif()
endif()

# Собирает быстрый стенд проверки вероятности наличия коллизий на общей таблице сообщений.
add_executable(collision_probability_study collision_probability_study.cpp)
if(MSVC)
  target_compile_options(collision_probability_study PRIVATE /utf-8 $<$<CONFIG:Release>:/O2>)
else()
  target_compile_options(collision_probability_study PRIVATE -O3)
endif()

# Проверяет основной BBHT и сохранённые экспериментальные точки входа.
option(GOST_BUILD_BBHT_TESTS "Собирать проверки BBHT" ON)
if(GOST_BUILD_BBHT_TESTS)
  enable_testing()
  add_executable(test_search_modules test_search_modules.cpp test_search_modules_odr.cpp)
  if(NOT MSVC)
    target_link_libraries(test_search_modules PRIVATE pthread)
  endif()
  add_test(NAME search_modules_odr COMMAND test_search_modules)
  foreach(bbht_test IN ITEMS test_bbht_adaptive test_bbht_large test_bbht_no_internal_deadline test_search_policy)
    add_executable(${bbht_test} ${bbht_test}.cpp)
    if(MSVC)
      target_compile_options(${bbht_test} PRIVATE /O2)
    else()
      target_compile_options(${bbht_test} PRIVATE -O3)
      target_link_libraries(${bbht_test} PRIVATE pthread)
    endif()
    add_test(NAME ${bbht_test} COMMAND ${bbht_test})
  endforeach()
  add_executable(bbht_full_worker bbht_full_worker.cpp)
  get_target_property(bbht_options gost_core COMPILE_OPTIONS)
  get_target_property(bbht_definitions gost_core COMPILE_DEFINITIONS)
  get_target_property(bbht_link_options gost_core LINK_OPTIONS)
  target_compile_options(bbht_full_worker PRIVATE ${bbht_options})
  target_compile_definitions(bbht_full_worker PRIVATE ${bbht_definitions})
  if(bbht_link_options)
    target_link_options(bbht_full_worker PRIVATE ${bbht_link_options})
  endif()
  if(NOT MSVC)
    target_link_libraries(bbht_full_worker PRIVATE pthread)
  endif()
endif()
