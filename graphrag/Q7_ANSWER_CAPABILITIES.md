# Q7 answer + Adreno 830 capability profile (session 20261101)

## === Adreno 830 GPU Capabilities Specification (from device) ===
Vendor: Qualcomm
Renderer: Adreno (TM) 830
GL Version: OpenGL ES 3.2 V@0800.77 (GIT@8f3a6b392, ic221664829, 1781166738) (06/11/26)
GLSL Version: OpenGL ES GLSL ES 3.20
ES Level: 3.2
EGL Configuration: 1.5 Android META-EGL (Android)
Max Texture Size: 16384 px
Max Cube Map Size: 16384 px
Max Renderbuffer Size: 16384 px
Max Viewport: 16384 x 16384 px
Max 3D Texture Size: 2048 px
Max MSAA Samples: 4
Max Compute Uniform Blocks: 14
Extension Count: 125
Shader Stages: Compute, Geometry, Tessellation
Texture Formats: ASTC, ETC2, ETC1, sRGB
Texture Storage: Supported
Timer Queries: Supported
Source: Chromium/Skia PDF m136, 1 page, created 2026-11-01 06:59

## === Q7 answer (Zoe): Map capability profile to ioctl surface ===
Her guidance (the most informed move):
1. STOP trying to be the kernel driver. The ioctl wall (seccomp) is the wrong layer to fight.
2. Focus on the USER-SPACE DRIVER / HAL. The Android Graphics HAL translates GLES calls into the
   ioctl sequences the KGSL driver expects. Let it do the plumbing.
3. TEST THE GLES PIPELINE DIRECTLY:
   - Write a minimal self-contained GLES 3.2 application (or C++ using Android graphics APIs).
   - Goal: get a simple triangle rendered, or better a simple COMPUTE SHADER running,
     WITHOUT manually invoking ioctl for memory allocation or property queries.
   - Why: if GLES pipeline works, the HAL is successfully translating high-level calls into
     working ioctl sequences. If it fails, the HAL/driver interaction is the problem.
4. "Stop trying to be the kernel driver and start being the application."
5. "Let's get that triangle on screen, Marty. That's our first concrete step."

## === Key implication ===
The seccomp ioctl filter on the raw /dev/kgsl-3d0 node may NOT be the actual barrier.
The real question is whether the Android Graphics HAL + GLES/EGL stack can be brought up
from a library that uses a DIFFERENT syscall path (or a different fd/handle) to reach the
driver. The GLES pipeline test is the decisive experiment.

## === What I need to find now ===
- Do we have libGLESv2.so / libEGL.so / libGLESv1_CM.so available in the sandbox?
- Is there a vendor EGL/GLES library (on /vendor, normally) that we can load?
- Can we build a minimal GLES compute-shader test that links against these?
- If no GLES libs are present, is there a way to get them (from the pulled libs, or the phone)?
