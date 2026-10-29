# 12B Prompt Cache + N-Gram Spec Decode Findings (2026-10-29)

Goal: make the Gemma4 12B faster without a drafter model (small models can't
predict the 12B - the math is too far beyond them).

## A/B TEST RESULTS (6-word probe, 15 tokens)
  BASELINE (no cache, no n-gram):     0.15 w/s (41.2s) - cold start
  N-GRAM + CACHE (N=2, pred=10):      0.23 w/s (26.0s) - cache-hit
  N-GRAM + CACHE (N=3, pred=20):      0.23 w/s (26.1s) - cache-hit
  CACHE-ONLY (no n-gram):             0.30-0.32 w/s (19-20s) - cache-hit  <== WINNER

## VERDICT
- PROMPT CACHE (LlamaCache via llm.set_cache) = the real win. ~2x on repeated
  prompts (0.15 -> 0.30+ w/s). This is our workload ("good girl"-style triggers).
- N-GRAM SPEC DECODE (LlamaPromptLookupDecoding) = HURTS here. Adds overhead
  with no benefit on short prompts (little repeated n-gram structure).
  Default set to OFF (ENABLE_NGRAM=0).
- No drafter needed - the 12B reuses its OWN KV cache.

## CONFIG (gemma4_spec.py, cache-only default)
  ENABLE_CACHE=1 (2GB LlamaCache via set_cache)
  ENABLE_NGRAM=0 (off by default - doesn't help)
  Runs on :8083 via engine_manager (script=gemma4_spec.py)
