# Native KleidiAI Build + Engine Manager Fix (2026-10-29)

## Problem
8-30 minute waits for model output. Gemma2-9B was ~0.1-1 tok/s. Ports collided
(every llama_cpp.server bound the same port).

## Root causes
1. The pip llama-cpp-python wheel was compiled for a GENERIC aarch64 baseline.
   It had NEON/FMA/FP16/DOTPROD but NOT KleidiAI (runtime-dispatched Arm CPU
   microkernel library). llama.cpp can pick the best CPU kernel at runtime when
   KleidiAI is built in.
2. The qroot bridge sets PORT=35449 globally. llama_cpp.server reads PORT env
   FIRST (server/__main__.py:93), so every server bound 35449 and collided.

## Fixes (both WORKED)
### 1. KleidiAI native build
CMAKE_ARGS="-DGGML_NATIVE=ON -DGGML_CPU_KLEIDIAI=ON -DGGML_OPENMP=ON"
cd /root/llama-cpp-python && git submodule update --init --recursive
uv pip install --python /root/.llm-venv/bin/python3 --force-reinstall .
Result: Gemma2-9B eval = 332.12 ms/token = 3.01 tok/s (was 0.1-1 tok/s), 3x-30x.
0.5B router 81.77 tok/s (was 52). 181-word scene: 76s (was 30 min). ~21x avg.

### 2. Engine Manager (port collision + memory-aware resident/on-demand)
/root/engine_manager.py
- Sets a UNIQUE PORT per engine (overrides the global PORT=35449).
- resident vs on-demand: small models (router/reranker/embedder) + storyteller
  (gemma2) stay UP; big models (dream 5.8GB, precision 5.1GB) load ON-DEMAND.
- Memory guard: won't OOM the box for a big model.
- embedder needs --embedding True (Qwen3-embedding).
Commands: status / start-resident / start-all / start <name> / stop <name> /
restart <name> / stop-all.

## Engine stack (all on distinct ports, native build)
  gemma2    :8083  resident  5.4GB  storyteller (direct API - server stalls)
  router    :8085  resident  0.6GB  qwen2.5-0.5b-instruct
  reranker  :8086  resident  0.6GB  qwen3-reranker-0.6b
  embedder  :8087  resident  0.6GB  Qwen3-Embedding-0.6B (--embedding True)
  dream     :8082  on-demand 5.8GB  Huihui-gemma-4-E4B
  precision :8080  on-demand 5.1GB  Qwen2.5-Coder-7B

## Remaining lever
GPU offload needs phone root or a native Android app for /vendor access (Vulkan
loader + Adreno ICD live on /vendor, not mounted in proot). KleidiAI native CPU
is the win until then.
