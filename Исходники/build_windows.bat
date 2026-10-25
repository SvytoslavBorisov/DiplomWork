@echo off
setlocal
cd /d "%~dp0"

where cmake >nul 2>nul
if errorlevel 1 goto :direct_msvc

cmake -S cpp_core -B build\cpp_core -DGOST_ENABLE_AVX2=OFF
if errorlevel 1 goto :fail
cmake --build build\cpp_core --config Release --clean-first
if errorlevel 1 goto :fail

if not exist bin mkdir bin
if exist build\cpp_core\Release\gost_core.exe (
  copy /Y build\cpp_core\Release\gost_core.exe bin\gost_core.exe >nul
) else (
  copy /Y build\cpp_core\gost_core.exe bin\gost_core.exe >nul
)
if errorlevel 1 goto :fail
if not exist bin\gost_core.exe goto :fail
goto :verify

:direct_msvc
set "VSDEV=C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\Common7\Tools\VsDevCmd.bat"
if not exist "%VSDEV%" (
  echo [ERROR] Neither CMake nor Visual Studio 2022 C++ Build Tools were found.
  goto :fail
)
echo [INFO] CMake not found; compiling directly with MSVC Release tools...
call "%VSDEV%" -arch=x64 -host_arch=x64
if errorlevel 1 goto :fail
if not exist bin mkdir bin
if not exist build\cpp_core mkdir build\cpp_core
cl.exe /utf-8 /nologo /std:c++17 /EHsc /O2 /GL /DNDEBUG /D_ITERATOR_DEBUG_LEVEL=0 cpp_core\gost_core.cpp /Fo:build\cpp_core\gost_core_candidate.obj /Fe:bin\gost_core_candidate.exe /link /LTCG /OPT:REF /OPT:ICF
if errorlevel 1 goto :fail
move /Y bin\gost_core_candidate.exe bin\gost_core.exe >nul
if errorlevel 1 goto :fail
if exist build\cpp_core\gost_core_candidate.obj del /q build\cpp_core\gost_core_candidate.obj

:verify
echo.
echo [OK] Compatible x64 Release C++ core built: bin\gost_core.exe
bin\gost_core.exe version
bin\gost_core.exe selftest-batch
if errorlevel 1 goto :fail
python tests\selftest_cpp.py
if errorlevel 1 goto :fail
python tests\selftest.py
if errorlevel 1 goto :fail
python tests\test_sigma_aware.py
if errorlevel 1 goto :fail

echo.
echo [OK] All self-tests passed.
if /I not "%~1"=="--no-pause" pause
exit /b 0

:fail
echo.
echo [ERROR] Build or self-test failed.
if /I not "%~1"=="--no-pause" pause
exit /b 1
