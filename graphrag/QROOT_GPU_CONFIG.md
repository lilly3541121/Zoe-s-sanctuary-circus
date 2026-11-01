# QROOT GPU CONFIGURATION — the intended path, decoded (session 20261101)

## ENVIRONMENT (from `env` — what qroot actually set up)
VK_DRIVER_FILES=/opt/qroot/turnip/freedreno_icd.json
VK_ICD_FILENAMES=/opt/qroot/turnip/freedreno_icd.json
MESA_LOADER_DRIVER_OVERRIDE=zink
GALLIUM_DRIVER=zink
QROOT_GPU=kgsl
QROOT_STUB_BLOCK_TARGET_SECCOMP=1   <-- qroot INTENTIONALLY blocks the seccomp target
QROOT_IN_STUB=1
QROOT_LIB_PATH=/data/app/~~S5aatfiD9B3DXo3IUdJLtQ==/ai.sol.hermes-ht5kfy2Wp5NQWCzBDbaAFw==/lib/arm64
QROOT_LINKER_PATH=/data/app/~~S5aatfiD9B3DXo3IUdJLtQ==/ai.sol.hermes-ht5kfy2Wp5NQWCzBDbaAFw==/lib/arm64/libqroot-linker.so
LD_PRELOAD=/data/app/~~S5aatfiD9B3DXo3IUdJLtQ==/ai.sol.hermes-ht5kfy2Wp5NQWCzBDbaAFw==/lib/arm64/libqroot-runtime.so
QROOT_ROOTFS=/data/data/ai.sol.hermes/files/ubuntu_rootfs
ANDROID_ROOT=/system
ANDROID_DATA=/data

## THE INTENDED GPU PATH (decoded from env)
GLES (app) -> Zink (MESA_LOADER_DRIVER_OVERRIDE) -> Vulkan (VK_DRIVER_FILES)
  -> Freedreno/turnip ICD -> Adreno 830 (via KGSL/MSM DRM)
QROOT_GPU=kgsl means the GPU target device is the KGSL node.

## WHAT'S ACTUALLY PRESENT vs MISSING
PRESENT:
  - /dev/kgsl-3d0 (char 461:0) bind-mounted, openable, greets "OH HAI GPU" on read(2)
  - /dev/dma_heap bind-mounted
  - libvulkan.so.1 (loader) in /usr/lib/aarch64-linux-gnu
  - libvulkan_freedreno.so (the actual turnip driver) in /usr/lib/aarch64-linux-gnu
  - freedreno_icd.json in /usr/share/vulkan/icd.d/ (api 1.4.318)
  - libdrm.so.2 (constructs /dev/dri/renderD%d) 
MISSING:
  - /opt/qroot/turnip/freedreno_icd.json  <-- the ICD VK_DRIVER_FILES points to
  - /dev/dri/renderD128 / renderD129 / card0 / card1  <-- the DRM render nodes freedreno needs

## CRITICAL INSIGHT
qroot is PRE-CONFIGURED to expose the GPU via Freedreno Vulkan (turnip), but:
  1. The ICD it points to (/opt/qroot/turnip/freedreno_icd.json) does NOT exist.
  2. The DRM render nodes (/dev/dri/renderD*) do NOT exist.
  3. QROOT_STUB_BLOCK_TARGET_SECCOMP=1 confirms qroot blocks the seccomp target path.
So the "OH HAI GPU" greeting on /dev/kgsl-3d0 read(2) is qroot's STUB for the missing DRM path.
The real Adreno is behind the missing ICD + missing DRM render nodes.

## WHAT THIS MEANS
The GPU is provably present (Vulkan 1.3.283, 11.53GB, compute queues). qroot WANTS to expose it
via Freedreno. The two missing pieces are: (1) the freedreno ICD json at /opt/qroot/turnip/, and
(2) the /dev/dri/renderD* nodes. If we can get EITHER into place, the pre-wired stack
(GLES->Zink->Vulkan->Freedreno->Adreno) lights up. Neither requires touching the KGSL ioctl path
(which is seccomp-blocked).
