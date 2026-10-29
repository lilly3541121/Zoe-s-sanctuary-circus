# E4B + Gemma3 Cleanup (2026-10-29)

User deleted Huihui-gemma-4-E4B-it-abliterated.Q6_K.gguf (5.8GB) and requested
all gemma3 removed.

CONFIRMED CLEAN:
- E4B file gone from app workspace, mirror, and mounted workspace
- No gemma3 file anywhere (1B was already gone; no other gemma3 files)
- E4B "dream" engine entry removed from engine_manager.py
- E4B "gemma" entry removed from engine.py (historical launcher)
- Nothing loaded in RAM (E4B was on-demand, not resident)

STACK AFTER CLEANUP (engine_manager.py):
  router :8085 | reranker :8086 | embedder :8087 | gemma4 :8083 (12B deep) |
  nidum :8088 (2B fast) | precision :8080 (7B coder, on-demand)
No dream engine (E4B gone). gemma-2-9b set aside on disk.
