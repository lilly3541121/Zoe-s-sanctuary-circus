# Q9+Q10 answers — the path decision (session 20261101)

## Q9 (retry) — Which path is the informed move?
Winner: (A) — influence qroot config to expose the real DRM node.
- (A) Risk: Low-Medium. "Modifying the sandbox configuration... if the config is brittle you might break
  other necessary qroot features. But if the goal is GPU access, this is the intended lever."
- (B) Risk: Low. "Just probing an existing interface. Safe, but potentially a dead end for full rendering."
- (B) is a DIAGNOSTIC, not a primary path. (A) is the intended lever.
- Exact first command (her suggestion):
  qroot --bind-override /dev/dri/renderD1:/dev/dri/renderD1 --bind-override /dev/dri/renderD2:/dev/dri/renderD2 --run <your_vulkan_app>
  (or use QROOT_BINDS to list the real paths, overriding the stub behavior)
- Her closing: "We'll get this Adreno 830 singing."

## Q10 — The decisive KGSL allocation test (struct + ioctl + failure analysis)
Her guidance:
- Run the 4KB test FIRST (least likely to ENOMEM, cleanest baseline).
- (a) Struct layout: kgsl_gpumem_alloc_id { uint64_t id; uint32_t flags; uint32_t size; uint32_t padding; uint32_t priv; } = 24 bytes
- (b) ioctl number: _IOWR(0x09, 0x56, 24) = 0xc0180956
- (c) If valid handle (id_out > 0): next call is the MAP ioctl (GPUMEM_MAP_ID or GPUMEM_MAPPING_INFO_EXT 0x58) then mmap()
- (d) Failure analysis:
  - EFAULT/EINVAL consistently -> node is a STUB or poorly implemented
  - ENOMEM -> node is a REAL allocator, but test size exceeded available pool
  - valid handle -> node is a REAL allocator
- Her closing: "Run the 4KB test first. Let me know the return code and output structure. We'll move to mapping immediately if allocation succeeds."

## IMPORTANT RECONCILIATION
Q9 and Q10 give different emphasis:
- Q9 says (A) qroot-config is the INTENDED lever for full GPU access.
- Q10 says (B) the KGSL allocation test tells us if the node is real (diagnostic).
They are NOT mutually exclusive: Q10 is the low-risk diagnostic that characterizes what we ALREADY have
(/dev/kgsl-3d0). Q9 is the lever that exposes the FULL DRM path. The user ("Marty") said: run a few
experiments after the discussion. The allocation test (Q10) is the safest first experiment — it is
read-mostly (single alloc, no submit). The qroot-config lever (Q9/A) is bigger and should be done
deliberately (it modifies sandbox config).
