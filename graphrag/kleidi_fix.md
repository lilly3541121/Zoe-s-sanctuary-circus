# Native KleidiAI Build Fix (2026-10-29)

Problem: 8-30 minute waits for model output. Gemma2-9B was ~0.1-1 tok/s (CPU-only
prebuilt wheel with generic aarch64 kernels).

Root cause: The pip llama-cpp-python wheel was compiled for a GENERIC aarch64
baseline - it had NEON/FMA/FP16/DOTPROD but NOT KleidiAI (the runtime-dispatched
Arm CPU microkernel library). llama.cpp can select the best CPU kernel at runtime
when KleidiAI is built in.

Fix: Built llama-cpp-python from source with:
  CMAKE_ARGS="-DGGML_NATIVE=ON -DGGML_CPU_KLEIDIAI=ON -DGGML_OPENMP=ON"
Build: /root/llama-cpp-python (git clone + submodule init)
Install: uv pip install --python /root/.llm-venv/bin/python3 --force-reinstall .

Result (measured via llama_perf_context_print):
  Gemma2-9B: eval time 332.12 ms/token = 3.01 tokens/s (was ~0.1-1 tok/s)
  = ~3x-30x speedup. A 181-word scene: 76s (was 30 min).
  0.5B router: 81.77 tokens/s (was ~52).

Verdict: GPU offload is NOT reachable in this proot sandbox (/vendor not mounted,
no Vulkan loader/ICD - the qroot bridge supports --gpu vulkan but it's an app-side
launch setting). But the KleidiAI native CPU build is a MASSIVE real speedup.

Next: The remaining big lever is GPU (needs phone root or native Android app for
/vendor access). For now, KleidiAI native is the win.
