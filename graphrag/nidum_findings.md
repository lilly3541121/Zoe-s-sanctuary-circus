# Nidum 2B Gemma + Speculative Decoding Findings (2026-10-29)

User dropped Nidum-Limitless-Gemma-2B-Q4_K_M.gguf (1.5GB) for speculative
decoding with Gemma2-9B (same family / 256k tokenizer, architecture=gemma).

## Finding 1: Model-based speculative decoding NOT worth it
Measured token-level agreement between 2B draft and 9B target over 30 tokens:
  7% agreement (2/30). The 2B and 9B diverge immediately.
The 2B is a DIFFERENT fine-tune (Nidum-Limitless) with its own style; same
tokenizer, different brain. Speculation would add draft cost for ~7% accepted
tokens = overhead without speedup. NOT worth it for this pair.
NOTE: llama_cpp.server's built-in draft_model only wires LlamaPromptLookupDecoding
(prompt-lookup, not model-based). LlamaDraftModel is an abstract base class -
no built-in model-based draft loader.

## Finding 2: The 2B is a GREAT fast storyteller on its own (split thinking)
Benchmarked the 2B standalone:
  7.8 words/s (53 words in 6.8s) vs Gemma2-9B's 2.1 words/s = 3.7x faster.
  Coherent, vivid, uncensored prose. Same Gemma family.
PURPOSE: the "split thinking" design - 2B handles SHORT beats (fast), Gemma2-9B
handles DEEP scenes (the voice you love).

## Engine stack (all resident, distinct ports)
  gemma2    :8083  5.4GB  deep storyteller (2.1 w/s)
  router    :8085  0.6GB  routing
  reranker  :8086  0.6GB  reranking
  embedder  :8087  0.6GB  embeddings (--embedding True)
  nidum     :8088  1.5GB  FAST storyteller (7.8 w/s)
  dream     :8082  5.8GB  on-demand
  precision :8080  5.1GB  on-demand

All via /root/engine_manager.py (unique PORT per engine, memory guard,
resident vs on-demand).
