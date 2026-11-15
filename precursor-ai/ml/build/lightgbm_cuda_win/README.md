# LightGBM 4.6.0 CUDA build on Windows (local, unofficial)

The PyPI LightGBM wheel is CPU-only. This folder reproduces the CUDA build used in `ml/.venv` (user request 2026-11-15).

- **Version:** 4.6.0, not 4.7.0. 4.7.0's CUDA build requires NCCL (no Windows build exists); 4.6.0 has no NCCL dependency.
- **Patch** (`lightgbm-4.6.0-win-cuda.patch`), all for MSVC + CUDA 13.2 compatibility, none changes algorithms:
  1. `CMakeLists.txt`: build only `sm_89` (RTX 4060). CUDA 13 dropped sm_60-72; other GPUs need this line edited.
  2. `cuda_single_gpu_tree_learner.cpp`: `1UL` -> `static_cast<size_t>(1)` (`unsigned long` is 32-bit on Windows).
  3. `meta.h`: `kMinScore/kMaxScore/kEpsilon/kZeroThreshold` made `constexpr` so device code can use them.
  4. `fmt/format.h`: a `U"\x9999999a..."` rounding-threshold table replaced by an equal-valued expression (nvcc's frontend rejects the literal).
- **Build flags:** `-DUSE_CUDA=ON`, CUDA flags `-Xcompiler=/utf-8 -DFMT_UNICODE=0`.
- **Verify:** `lgb.LGBMClassifier(device_type="cuda").fit(X, y)` works; 2M x 40 rows, 200 trees: 6.1 s GPU (peak 78% util) vs 11.5 s CPU.
- Unofficial and unsupported by LightGBM. Use `device_type="cpu"` if a result must match an official wheel exactly; GPU histogram training is not bit-identical to CPU, so log the device in `meta.json`.
- Running `uv pip install -r ml/requirements.txt` replaces this build with the CPU wheel; rerun `build.bat` afterwards.
