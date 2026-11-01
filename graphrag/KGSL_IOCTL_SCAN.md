# KGSL ioctl command scan results (read-only, zeroed 24-byte buf)
# session 20261101 — this is the "dump the ioctl list" SuperGemma asked for.

## WHAT RETURNED ret=0 (command got THROUGH seccomp AND the driver accepted it)
# All direction/size combos returned 0 for the SAME nr values -> matched on nr field only.
# Standard msm_kgsl.h ABI correlation:
0x38 = KGSL_IOCTL_GPUOBJ_DESTROY_ID          -> ret 0
0x39 = KGSL_IOCTL_GPUOBJ_IMPORT_RAW          -> ret 0
0x3a = KGSL_IOCTL_GPUOBJ_IMPORT_PRIVATE      -> ret 0
0x40 = KGSL_IOCTL_GET_SPM_INFO               -> ret 0
0x56 = KGSL_IOCTL_GPUMEM_ALLOC_ID            -> ret 0   <-- GPU MEMORY ALLOCATOR
0x58 = KGSL_IOCTL_GPUMEM_MAPPING_INFO_EXT    -> ret 0

## WHAT RETURNED NON-ZERO (reached driver, driver rejected/blocked)
0x15 = KGSL_IOCTL_CONTEXT_GETSPMSTATE        -> EOPNOTSUPP (95)
0x20 = KGSL_IOCTL_SHAREDMEM_FROM_PHYSPOOL    -> EOPNOTSUPP (95)
0x32 = KGSL_IOCTL_MAP_USER_MEM               -> ENODEV (19)
0x3b = KGSL_IOCTL_GPUOBJ_SYNC                -> EPERM (1)
0x48 = KGSL_IOCTL_CONTEXT_GETPROP            -> errno 524 (vendor-specific?)
0x4b = KGSL_IOCTL_CONTEXT_GETPROP_EXT        -> EOPNOTSUPP (95)
0x5a = KGSL_IOCTL_GPUMEM_MAPPING_INFO_EXT_V2 -> ENODEV (19)
0x5b = KGSL_IOCTL_GET_GPU_INFO               -> EAGAIN (11)
0x5c = KGSL_IOCTL_GET_GPU_MMU_INFO           -> ENODEV (19)
0x5d = KGSL_IOCTL_GET_GPU_STATE              -> ENODEV (19)

## CRITICAL OBSERVATIONS
1. The ioctls returning 0 match on the nr field ONLY (same result across all direction/size).
2. Standard KGSL GETPROP (nr 1/3/5/8) returned EINVAL(25) — the driver does NOT implement the classic
   KGSL_IOCTL_DEVICE_GETPROP path. That is unusual for a real kgsl driver.
3. read(2) returns the ASCII greeting b'OH HAI GPU\n\x00' — real device drivers do NOT do this.
4. Hypothesis to test: /dev/kgsl-3d0 is a qroot GPU FACADE/SHIM, not the raw Adreno driver.
   It greets on read and accepts a curated set of degenerate ioctls (returning 0), but does NOT
   expose the real command-submission path. The real driver sits behind the mount/SELinux wall.
5. ALTERNATIVE hypothesis: it IS real, and GPUMEM_ALLOC_ID (0x56) genuinely allocates GPU memory
   (a zeroed request returns id 0 / 0-byte alloc). If so, calling 0x56 with a REAL allocation
   request would return a valid handle — and that is a genuine route to a GPU-mappable buffer.

## DISTINGUISHING TEST (needs her sign-off — it allocates, don't run blind)
Call KGSL_IOCTL_GPUMEM_ALLOC_ID (0x56) with a REAL nonzero size. If it returns a valid id/handle
and no error -> real allocator, we have a route. If it returns 0/garbage -> confirmed shim.
