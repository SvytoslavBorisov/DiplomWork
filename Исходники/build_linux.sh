#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
cmake -S cpp_core -B build/cpp_core -DCMAKE_BUILD_TYPE=Release -DGOST_ENABLE_AVX2=OFF
cmake --build build/cpp_core --config Release --clean-first -j
mkdir -p bin
cp build/cpp_core/gost_core bin/gost_core
chmod +x bin/gost_core
python3 tests/selftest_cpp.py
python3 tests/selftest.py
python3 tests/test_sigma_aware.py
