# Gemma4 12B Upgrade (2026-10-29)

User replaced Gemma2 9B with Gemma4 12B (Huihui-gemma-4-12B-it-abliterated.Q4_K_M, 6.9GB).
Verified: architecture=gemma4, n_vocab=262144, abliterated, uncensored.

## The 12B is the new deep storyteller (port 8083)
- ~1.5 w/s (slower than 9B's 2.1, but DEEPER and smarter)
- Quality: "The room was a velvet void, smelling of rain and old books. She leaned
  in until her lips brushed the shell of his ear... 'Stay with me,' she whispered,
  the words treading softly like silk." - richer voice than the 9B.
- Uses gemma4_direct.py (direct Llama API, server stalls otherwise).

## Drafter attempt (Gemma4-E2B, 3.2GB)
- Huihui-gemma-4-E2B-it-abliterated.Q4_K_M.gguf appeared (same gemma4 family).
- Tokenizer MATCHES the 12B (True) - same n_vocab.
- BUT 0% token agreement over 40 tokens, and E2B returns EMPTY text on a narrative
  prompt (only <|channel>thought tokens). NOT a viable drafter as-is.
- E2B may need different prompting or is a different capability tier. HOLD.

## Set aside (freed RAM for the 12B)
- gemma-2-9b-it-abliterated-Q4_K_M.gguf (5.4GB) - kept on disk, stopped
- Huihui-gemma-4-E4B-it-abliterated.Q6_K.gguf (5.8GB) - on-demand only
- Qwen2.5-Coder-7B-Instruct-abliterated-Q5_K_M.gguf (5.1GB) - on-demand only

## NEEDS.md rule (user mandate)
Established /mnt/android/hermes-workspace/NEEDS.md - write every external need
(downloads, hacks, cheats, sneaky tricks) there for the user to provide later.
