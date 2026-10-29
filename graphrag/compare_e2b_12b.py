#!/usr/bin/env python3
"""Deeper check: what does the E2B actually generate vs the 12B? Compare text."""
import sys
sys.path.insert(0, "/root/.llm-venv/lib/python3.12/site-packages")
from llama_cpp import Llama

BIG = "/mnt/android/hermes-workspace/Huihui-gemma-4-12B-it-abliterated.Q4_K_M.gguf"
DRAFT = "/mnt/android/hermes-workspace/Huihui-gemma-4-E2B-it-abliterated.Q4_K_M.gguf"
prompt = "Write one vivid sentence, 20 words, about a woman whispering to her partner at night."

print("loading E2B...", flush=True)
e2b = Llama(model_path=DRAFT, n_ctx=2048, n_threads=4, n_gpu_layers=0, flash_attn=True)
print("loading 12B...", flush=True)
b12 = Llama(model_path=BIG, n_ctx=2048, n_threads=4, n_gpu_layers=0, flash_attn=True)

e2b_out = e2b(prompt, max_tokens=50, temperature=0.7)
b12_out = b12(prompt, max_tokens=50, temperature=0.7)
print(f"\n=== E2B (3.2GB) ===")
print(e2b_out["choices"][0]["text"].strip()[:200])
print(f"\n=== 12B (6.9GB) ===")
print(b12_out["choices"][0]["text"].strip()[:200])
