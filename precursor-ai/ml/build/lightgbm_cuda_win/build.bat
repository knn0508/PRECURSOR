@echo off
REM Build LightGBM 4.6.0 with CUDA on Windows (MSVC + CUDA 13.2, target RTX 4060 = sm_89).
REM Run from precursor-ai/. Needs: VS 2026 BuildTools (C++), CUDA toolkit, uv, ml/.venv. See README.md.
REM 4.7.0 cannot be used: its CUDA path requires NCCL, which has no Windows build.
setlocal
call "C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\VC\Auxiliary\Build\vcvars64.bat" || exit /b 1
set WORK=%TEMP%\lgbm_cuda_build
rmdir /s /q "%WORK%" 2>nul & mkdir "%WORK%"
curl -sL -o "%WORK%\s.tgz" https://files.pythonhosted.org/packages/source/l/lightgbm/lightgbm-4.6.0.tar.gz || exit /b 1
tar xzf "%WORK%\s.tgz" -C "%WORK%" || exit /b 1
cd /d "%WORK%\lightgbm-4.6.0"
git apply -p0 --ignore-whitespace --whitespace=nowarn "%~dp0lightgbm-4.6.0-win-cuda.patch" || exit /b 1
set CMAKE_GENERATOR=Ninja
set CMAKE_ARGS=-DUSE_CUDA=ON "-DCMAKE_CUDA_FLAGS=-Xcompiler=/utf-8 -DFMT_UNICODE=0"
set CUDACXX=%CUDA_PATH%\bin\nvcc.exe
cd /d "%~dp0..\.."
uv pip install --python .venv\Scripts\python.exe --reinstall --no-cache "%WORK%\lightgbm-4.6.0" -v
