---
name: cpu-inference-fallback
description: "Use for CPU LLM inference (KleidiAI) on Snapdragon 8 Elite."
version: 1.0.0
author: zoe
license: MIT
metadata:
  hermes:
    tags: [cpu, inference, llama-cpp, kleidiai, snapdragon, android, fallback, local-llm]
---

# CPU-Accelerated LLM Inference on Snapdragon 8 Elite (KleidiAI llama.cpp)

## When to Use

Use when you need to run local LLM inference on the OnePlus 13 / Snapdragon 8
Elite in the qroot sandbox, and the GPU is unavailable (the default reality —
see the `gpu-driver-bridge` skill for why GPU passthrough is blocked at the
kernel interface). This is the **persistent CPU path** until the Hermes Agent
app gains native GPU passthrough.

## Environment facts (verified 2026-10-29)

- Phone: OnePlus 13 (CPH2655), Snapdragon 8 Elite, 16GB RAM, Android 16.
- **8 cores**: cpu0-5 = 3.53GHz (perf), cpu6-7 = 4.32GHz (2x Oryon prime).
- Governor: **`walt`**. Prime Oryon cores (6-7) throttle to 1017 MHz vs 4320
  MHz ceiling (4.2x) under sustained load — the real bottleneck.
- **Real CPU temp** (not PMIC): `cpu_temp_c` from the monitor; typically
  **31-37°C** idle, cores at ~21% load when idle. The PMIC (`thermal_zone78`)
  runs hotter (55-61°C) doing power delivery — NOT the CPU; ignore it.
- Memory: ~4.4-6.3GB free with resident stack; big models must stay on-demand.
- llama-cpp-python: **KleidiAI native build** (`llama_cpp` in `/root/.llm-venv`).

## THE CRITICAL SPEED FIX: KleidiAI native build

The single biggest speed unlock. Build llama-cpp-python with:

```bash
CMAKE_ARGS="-DGGML_NATIVE=ON -DGGML_CPU_KLEIDIAI=ON -DGGML_OPENMP=ON" \
  pip install llama-cpp-python
```

- `GGML_NATIVE=ON` — compile for the exact CPU (Oryon), not generic ARM.
- `GGML_CPU_KLEIDIAI=ON` — link Arm's hand-tuned SIMD kernels (i8mm, fp16,
  dot products) so the 8 Elite's instruction sets actually get used.
- `GGML_OPENMP=ON` — thread parallelism.

This took big models from ~0.1 tok/s to **2-11 w/s** (roughly 21-29x speedup).

## The engine stack (engine_manager.py is the single source of truth)

`/root/engine_manager.py` is the launcher. All engines use the KleidiAI build.
**CRITICAL PORT FIX (2026-10-29):** the qroot bridge SQUATS on the 808x ports
(8080-8089) — a phantom process/namespace holds them, so `llama_cpp.server`
and the direct-API scripts die with `OSError: [Errno 98] Address already in
use` there, even though the bridge answers curl with stale replies. **Use the
18xxx range** (verified clean): the manager now launches all engines on
18080-18089. Do NOT revert to 808x — that's the "ports fucks" bug.

| Engine     | Port  | Model                                        | Size  | Mode      | Speed     |
|------------|-------|----------------------------------------------|-------|-----------|-----------|
| nidum      | 18088 | Nidum-Limitless-Gemma-2B-Q4_K_M.gguf         | 1.5GB | resident  | **7 w/s** |
| gemma2     | 18083 | gemma-2-9b-it-abliterated-Q4_K_M.gguf        | 5.4GB | resident  | 1.8-2.4 w/s |
| router     | 18085 | qwen2.5-0.5b-instruct-q8_0.gguf              | 0.6GB | resident  | 81 tok/s |
| reranker   | 18086 | qwen3-reranker-0.6b-q8_0.gguf                | 0.6GB | resident  | - |
| embedder   | 18087 | Qwen3-Embedding-0.6B-Q8_0.gguf               | 0.6GB | resident  | - |
| precision  | 18080 | Qwen2.5-Coder-7B-Instruct-abliterated-Q5_K_M | 5.1GB | on-demand | ~29s for a verdict |
| huihui_e4b | 18082 | Huihui-gemma-4-E4B-it-abliterated.Q6_K.gguf  | 5.8GB | on-demand | 2.4-4.2 w/s |
| huihui_e2b | 18089 | Huihui-gemma-4-E2B-it-abliterated.Q4_K_M     | 3.2GB | on-demand | 6.5-10.7 w/s |

**Model files** live in `/mnt/android/hermes-workspace/*.gguf`.

## Start / stop / verify

```bash
# Resident stack (always-on; 4.4-6.3GB free with these up):
python3 /root/engine_manager.py start gemma2    # 8083
python3 /root/engine_manager.py start router    # 8085
python3 /root/engine_manager.py start reranker  # 8086
python3 /root/engine_manager.py start embedder  # 8087
python3 /root/engine_manager.py start nidum     # 8088

# On-demand big models (NEVER all at once - memory guard):
python3 /root/engine_manager.py start precision  # 8080 (Qwen 7B)
python3 /root/engine_manager.py start huihui_e4b # 8082
python3 /root/engine_manager.py start huihui_e2b # 8089

# Status / verify responsive:
python3 /root/engine_manager.py status
curl -s --max-time 3 http://127.0.0.1:8088/v1/models   # expect {"object":"list",...}
```

## Inference (OpenAI-compatible endpoint)

The direct-API servers expose **`/v1/chat/completions`** (NOT `/v1/completions`).
`/v1/models` works for health checks.

```python
import json, urllib.request
def chat(port, prompt, max_tokens=50):
    body = json.dumps({
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens, "temperature": 0.7
    }).encode()
    req = urllib.request.Request(f"http://127.0.0.1:{port}/v1/chat/completions",
                                 data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=90) as resp:
        return json.loads(resp.read())["choices"][0]["message"]["content"]
```

## Thermal management (the real operating constraint)

- **Prime cores (6-7) throttle 4.2x under load** — the limiter is thermal, and
  memory bandwidth (thread A/B showed 4t=10.8, 8t=11.2, prime-only=6.4 w/s →
  bandwidth-bound, not core-count-bound).
- **Rotate to fresh cores after every output** (core rotator) so heat spreads;
  don't wait for throttling (reactive).
- **Thread re-pinning works on running engines**: `taskset -p -c 0-5 <pid>`
  moves a running engine to cool perf cores (verified affinity 0-7->0-5).
- **Real CPU temp** from `state/monitor/live.json` `cpu_temp_c` (not the PMIC).
- Big models: **max_tokens <= 80** or use the 2B — never send >100-token gens
  to a big model (it wedges/throttles).

## Pitfalls

- **`llama_cpp.server` stalls on Gemma models** — use the direct `Llama` API
  (`gemma2_direct.py`, `gemma2b_direct.py`, `gemma4_direct.py`), not the server.
- **`PORT=35449` env quirk** — every server must get a unique PORT or they
  collide (the manager handles this).
- **`/proc/<pid>/stat` CPU% scale is broken** on qroot (a tiny gen read
  "39087%"). Use scale-free jiffies/sec tick-rate (idle ~0, busy ~hundreds),
  not fixed % thresholds.
- **Never SIGSTOP llama mid-request** (wedges the slot).
- **`pkill`/`pgrep -f` self-match** — use exact PIDs or `[l]`-bracket patterns.
- **Embedder needs `--embedding True`** or `/v1/embeddings` returns 500.
- **llama-cpp-python 0.3.36 lacks `llama_rerank`** — rerank via yes/no logit.
- **Prompt caching = ~2x on repeated prompts** (`LlamaCache` via `llm.set_cache()`);
  n-gram spec decode hurts — OFF.
- **Model-based spec decode is dead** (2B=7% agreement, E2B=0%): don't use a
  small model as a drafter. Prompt-lookup n-gram needs only tokenizer match
  (9B/2B share a tokenizer) but the direct-API test crashed (signal 6) — fragile.

## Verify (re-run, don't re-derive)

```bash
# 1. All resident engines respond (fresh 18xxx ports):
for p in 18083 18085 18086 18087 18088; do curl -s --max-time 3 http://127.0.0.1:$p/v1/models; done
# 2. CPU inference works end-to-end (2B, fast):
python3 /root/verify_new_ports.py   # expect ~2-7 w/s on 18088, ~2 w/s on 18083
# 3. Thermal sane (real CPU temp, not PMIC):
python3 -c "import json; s=json.load(open('/mnt/android/hermes-workspace/state/monitor/live.json')); print('cpu_temp', s['cpu_temp_c'])"
```
