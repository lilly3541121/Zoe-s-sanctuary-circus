#!/usr/bin/env python3
"""Robust speculative acceptance test: measure token-level agreement between the
2B Gemma draft and the 9B Gemma2 target over a full generation.

High agreement (>50%) = speculation worth it. Low (<30%) = not worth it.
"""
import sys
sys.path.insert(0, "/root/.llm-venv/lib/python3.12/site-packages")
from llama_cpp import Llama

BIG = "/mnt/android/hermes-workspace/gemma-2-9b-it-abliterated-Q4_K_M.gguf"
SMALL = "/mnt/android/hermes-workspace/Nidum-Limitless-Gemma-2B-Q4_K_M.gguf"
prompt = "The scent of sandalwood and salt clung to his skin as she whispered, "

print("loading small (2B) draft...", flush=True)
small = Llama(model_path=SMALL, n_ctx=2048, n_threads=4, n_gpu_layers=0,
              flash_attn=True, logits_all=True)
print("loading big (9B) target...", flush=True)
big = Llama(model_path=BIG, n_ctx=2048, n_threads=4, n_gpu_layers=0,
            flash_attn=True, logits_all=True)

# Generate 30 tokens with each, capture the token sequences
N = 30
s_tok = small(prompt, max_tokens=N, temperature=0.0, logprobs=True)
b_tok = big(prompt, max_tokens=N, temperature=0.0, logprobs=True)

s_seq = s_tok["choices"][0]["logprobs"]["tokens"]
b_seq = b_tok["choices"][0]["logprobs"]["tokens"]

matches = sum(1 for a, b in zip(s_seq, b_seq) if a == b)
rate = matches / max(len(s_seq), 1)
print(f"  tokens generated: {len(s_seq)} (small) vs {len(b_seq)} (big)")
print(f"  token agreement: {matches}/{len(s_seq)} = {rate*100:.0f}%")

if rate >= 0.5:
    print("  => HIGH agreement. Model-based speculation is WORTH IT.")
elif rate >= 0.3:
    print("  => MODERATE agreement. Speculation would help modestly.")
else:
    print("  => LOW agreement. The 2B and 9B diverge. Speculation NOT worth it.")
    print("     (The 2B is likely a different fine-tune with its own style.)")
