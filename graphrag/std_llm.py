#!/usr/bin/env python3
"""std_llm.py — the STANDARD model-loading config for every Llama() instantiation.

Directive (2026-10-28): enforce KV cache quantization (type_k=8, type_v=8, Q8_0)
and n-gram speculation (LlamaPromptLookupDecoding(max_ngram_size=3, num_pred_tokens=2))
as the default for EVERY GGUF model we instantiate, to keep memory bandwidth open.

Usage:
    from std_llm import make_llm
    llm = make_llm(model_path=..., n_ctx=4096, embedding=True, n_threads=4)

make_llm() always applies:
    use_mlock=True, flash_attn=True, type_k=8, type_v=8,
    draft_model=LlamaPromptLookupDecoding(max_ngram_size=3, num_pred_tokens=2)
Overrides are merged on top (n_ctx, embedding, n_threads, n_gpu_layers).
"""
from llama_cpp import Llama
from llama_cpp.llama_speculative import LlamaPromptLookupDecoding

# The standard speculative draft (n-gram lookup, no extra weights).
STANDARD_DRAFT = LlamaPromptLookupDecoding(max_ngram_size=3, num_pred_tokens=2)


def make_llm(model_path, n_ctx=8192, n_threads=4, embedding=False, n_gpu_layers=0,
             verbose=False, **overrides):
    """Build a Llama with the STANDARD CPU-optimized config.

    KV cache quantized to Q8_0 (type_k=8, type_v=8) + flash attention + mlock +
    n-gram speculative decoding. Overrides (kwargs) win over the standard values.
    """
    # The draft_model is only meaningful for text generation, not embeddings.
    # But it's harmless for embedding=True (tested). Keep it standard per directive.
    kwargs = dict(
        model_path=model_path,
        n_ctx=n_ctx,
        n_threads=n_threads,
        use_mlock=True,
        flash_attn=True,
        type_k=8,
        type_v=8,
        draft_model=STANDARD_DRAFT,
        embedding=embedding,
        n_gpu_layers=n_gpu_layers,
        verbose=verbose,
    )
    kwargs.update(overrides)  # caller overrides win
    return Llama(**kwargs)
