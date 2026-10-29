# E2B speed test (2026-10-29)

E2B (Huihui-gemma-4-E2B-it-abliterated.Q4_K_M.gguf, 3.19GB, on-demand :8089)
measured with KleidiAI native build + direct API + unique PORT:

- Short beat: 12 words / 1.9s = 6.45 w/s. ("The single candle wept a trembling,
  golden tear into the suffocating black.")
- Longer gen: 90 words / 8.4s = 10.70 w/s. ("The station was a cavern of shadows...")

Fastest full storyteller in the swarm (beats 2B's 7.8 w/s on longer gens, bigger
model = deeper quality). Ran cool (54.1C max, 5.6GB free).

Rotator caught the E2B cycle: pid 24480 BUSY(491 t/s)->ready on 0-5, output
DONE->rotate to 0-7 (alternated to all-cores when prime cooled). System integrated.
