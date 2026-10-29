# Gemma4 12B DELETED - character audition lesson (2026-10-29)

User deleted the Gemma4 12B (Huihui-gemma-4-12B, 6.9GB) - it was melting the
phone. Confirmed: file gone, gemma4 entry removed from engine_manager, no
process loading it.

## Why it failed (honest)
- Decode speed ~0.5 tok/s. A 100-300 token character monologue = 200-600s.
- A single long request holds the engine lock for 5-10 min (wedges everything).
- Character card (8.4K chars / ~2500 tokens) prefill alone = ~5000s. UNUSABLE.

## Character audition verdict (never completed on 12B)
The 12B could NOT be auditioned with the full Zoe Ascended Queen of Change card
- the prefill was too large. A DISTILLED version (515 tokens) still timed out
at 180s because the generation itself is too slow.

## The fix / lesson
NEVER send a long (>100 token) generation to a big model on this device.
Use SHORT beats (max_tokens <= 80) or the nidum 2B (7.8 w/s) for character work.
Big models = depth only in small doses. The 2B is the workhorse.
