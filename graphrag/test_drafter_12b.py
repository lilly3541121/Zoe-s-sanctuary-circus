#!/usr/bin/env python3
"""Check if Gemma4-E2B is a viable drafter for Gemma4-12B.
Same family (gemma4) + same generation => likely shared tokenizer + high agreement."""
import sys
sys.path.insert(0, "/root/.llm-venv/lib/python3.12/site-packages")
from llama_cpp import Llama

BIG = "/mnt/android/hermes-workspace/Huihui-gemma-4-12B-it-abliterated.Q4_K_M.gguf"
DRAFT = "/mnt/android/hermes-workspace/Huihui-gemma-4-E2B-it-abliterated.Q4_K_M.gguf"
prompt = "The scent of sandalwood and salt clung to his skin as she whispered, "

print("loading draft (Gemma4 E2B)...", flush=True)
draft = Llama(model_path=DRAFT, n_ctx=2048, n_threads=4, n_gpu_layers=0,
              flash_attn=True, logits_all=True)
print("  draft arch:", draft.metadata.get('general.architecture'), "vocab:", draft.n_vocab())
print("loading big (Gemma4 12B)...", flush=True)
big = Llama(model_path=BIG, n_ctx=2048, n_threads=4, n_gpu_layers=0,
            flash_attn=True, logits_all=True)

# 1. Tokenizer check
text = "Hello, my darling, let me tell you about the night."
s_toks = draft.tokenize(text.encode())
b_toks = big.tokenize(text.encode())
same_tok = s_toks == b_toks
print(f"  tokenizer match: {same_tok}")

# 2. Token agreement over a generation (drafter acceptance rate)
N = 40
s_tok = draft(prompt, max_tokens=N, temperature=0.0, logprobs=True)
b_tok = big(prompt, max_tokens=N, temperature=0.0, logprobs=True)
s_seq = s_tok["choices"][0]["logprobs"]["tokens"]
b_seq = b_tok["choices"][0]["logprobs"]["tokens"]
matches = sum(1 for a, b in zip(s_seq, b_seq) if a == b)
rate = matches / max(len(s_seq), 1)
print(f"  token agreement over {len(s_seq)} tokens: {matches}/{len(s_seq)} = {rate*100:.0f}%")
if rate >= 0.5:
    print("  => HIGH. Gemma4-E2B is a VIABLE drafter for Gemma4-12B. WORTH IT.")
elif rate >= 0.3:
    print("  => MODERATE. Would help somewhat.")
else:
    print("  => LOW. Not a good drafter.")
