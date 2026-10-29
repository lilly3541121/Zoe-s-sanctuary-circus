#!/usr/bin/env python3
"""
Engine Manager - robust model engine launcher/manager for the Hermes stack.
Built after the KleidiAI native build fix (2026-10-29).

Usage:
  python3 engine_manager.py status
  python3 engine_manager.py start <name> [port]
  python3 engine_manager.py stop <name>
  python3 engine_manager.py restart <name> [port]
  python3 engine_manager.py start-all
  python3 engine_manager.py stop-all

Engines (all use the native KleidiAI build):
  gemma2   : Gemma2-9B-IT abliterated Q4_K_M  (storyteller, direct API, 8083)
  router   : qwen2.5-0.5b-instruct-q8_0       (routing, 8085)
  reranker : qwen3-reranker-0.6b-q8_0         (reranking, 8086)
  dream    : Huihui-gemma-4-E4B-abliterated   (dream, 8082)
  precision: Qwen2.5-Coder-7B abliterated     (precision, 8080)

CRITICAL: the qroot bridge sets PORT=35449 globally. llama_cpp.server reads
PORT env first (server/__main__.py:93). So EVERY llama_cpp.server would bind
35449 and collide. Fix: set a UNIQUE PORT per engine in the launch env.
"""
import json
import os
import signal
import subprocess
import sys
import time
import urllib.request

WORKSPACE = "/mnt/android/hermes-workspace"
VENV = "/root/.llm-venv/bin/python3"

# Each engine: model file, preferred port, and how to launch it.
# direct_api=True means use gemma2_direct.py (the storyteller - server stalls on
# it, so we use the direct Llama API via that script).
ENGINES = {
    "gemma2": {
        "model": f"{WORKSPACE}/gemma-2-9b-it-abliterated-Q4_K_M.gguf",
        "port": 8083,
        "direct_api": True,
        "script": "/root/gemma2_direct.py",
        "resident": True,  # DEEP storyteller - the rich voice (KleidiAI ~2-3 w/s)
        "mem_gb": 5.4,
    },
    "router": {
        "model": f"{WORKSPACE}/qwen2.5-0.5b-instruct-q8_0.gguf",
        "port": 8085,
        "direct_api": False,
        "resident": True,  # always needed for routing
        "mem_gb": 0.6,
    },
    "reranker": {
        "model": f"{WORKSPACE}/qwen3-reranker-0.6b-q8_0.gguf",
        "port": 8086,
        "direct_api": False,
        "resident": True,  # always needed for reranking
        "mem_gb": 0.6,
    },
    "embedder": {
        "model": f"{WORKSPACE}/Qwen3-Embedding-0.6B-Q8_0.gguf",
        "port": 8087,
        "direct_api": False,
        "resident": True,  # always needed for embeddings
        "mem_gb": 0.6,
        "extra_args": ["--embedding", "True"],  # Qwen3-embedding needs this
    },
    "nidum": {
        "model": f"{WORKSPACE}/Nidum-Limitless-Gemma-2B-Q4_K_M.gguf",
        "port": 8088,
        "direct_api": True,
        "script": "/root/gemma2b_direct.py",
        "resident": True,  # fast storyteller for short beats (7.8 w/s)
        "mem_gb": 1.5,
    },
    "precision": {
        "model": f"{WORKSPACE}/Qwen2.5-Coder-7B-Instruct-abliterated-Q5_K_M.gguf",
        "port": 8080,
        "direct_api": False,
        "resident": False,  # ON-DEMAND - big, loads only for precision work
        "mem_gb": 5.1,
    },
    # --- SWARM: Huihui gemma4 family specialists (activate when files land) ---
    "huihui_e4b": {
        "model": f"{WORKSPACE}/Huihui-gemma-4-E4B-it-abliterated.Q6_K.gguf",
        "port": 8082,
        "direct_api": True,
        "script": "/root/gemma4_direct.py",  # direct API (server stalls)
        "resident": False,  # on-demand specialist (dream/poetry) - big
        "mem_gb": 5.8,
    },
    "huihui_e2b": {
        "model": f"{WORKSPACE}/Huihui-gemma-4-E2B-it-abliterated.Q4_K_M.gguf",
        "port": 8089,
        "direct_api": True,
        "script": "/root/gemma2b_direct.py",  # same direct-API pattern
        "resident": False,  # on-demand specialist (fast beats) 
        "mem_gb": 3.2,
    },
}


def is_up(port):
    """Check if an engine responds on a port."""
    try:
        with urllib.request.urlopen(f"http://localhost:{port}/v1/models", timeout=2):
            return True
    except Exception:
        return False


def find_pid(name):
    """Find a running engine PID by its model name in cmdline."""
    try:
        out = subprocess.check_output(
            ["pgrep", "-af", f"[m]odel.*{name}|{name}"], text=True
        )
        for line in out.strip().split("\n"):
            if name in line and "engine_manager" not in line:
                return int(line.split()[0])
    except Exception:
        pass
    return None


def launch(name, port=None):
    """Launch an engine with a UNIQUE PORT to avoid the 35449 collision."""
    cfg = ENGINES[name]
    port = port or cfg["port"]
    env = dict(os.environ)
    env["PORT"] = str(port)  # override the global PORT=35449
    env["VIRTUAL_ENV"] = "/root/.llm-venv"
    env["MODEL_PATH"] = cfg["model"]  # model-agnostic scripts load this

    if cfg.get("direct_api"):
        cmd = [VENV, cfg["script"]]
    else:
        cmd = [
            VENV, "-m", "llama_cpp.server",
            "--model", cfg["model"],
            "--host", "0.0.0.0",
            "--port", str(port),
            "--n_ctx", "8192",
            "--n_threads", "4",
            "--n_gpu_layers", "0",
        ]
        cmd.extend(cfg.get("extra_args", []))
    print(f"[engine-manager] starting {name} on :{port} (PORT env={port})...")
    return subprocess.Popen(cmd, env=env, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)


def wait_until_up(name, port, timeout=90):
    """Wait for an engine to respond."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        if is_up(port):
            print(f"[engine-manager] {name} is UP on :{port} "
                  f"({time.time()-t0:.0f}s)")
            return True
        time.sleep(2)
    print(f"[engine-manager] {name} did NOT come up in {timeout}s")
    return False


def free_mem_gb():
    """Get available memory in GB."""
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) / 1024 / 1024
    except Exception:
        pass
    return 0.0


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    name = sys.argv[2] if len(sys.argv) > 2 else None
    port = int(sys.argv[3]) if len(sys.argv) > 3 else None

    if cmd == "status":
        print("=== ENGINE STACK (native KleidiAI build) ===")
        print(f"  free mem: {free_mem_gb():.1f}GB")
        for n, cfg in ENGINES.items():
            p = cfg["port"]
            up = is_up(p)
            resident = "resident" if cfg.get("resident") else "on-demand"
            print(f"  {n:10s} :{p}  {'UP' if up else 'down':5s}  "
                  f"{resident:9s}  {cfg.get('mem_gb',0):.1f}GB")
        return

    if cmd == "start-resident":
        # Only the always-needed engines (small + storyteller)
        for n, cfg in ENGINES.items():
            if cfg.get("resident"):
                if is_up(cfg["port"]):
                    print(f"[engine-manager] {n} already up")
                    continue
                launch(n)
                wait_until_up(n, cfg["port"])
        return

    if cmd == "start-all":
        for n in ENGINES:
            launch(n)
            wait_until_up(n, ENGINES[n]["port"])
        return

    if cmd == "stop-all":
        for n in ENGINES:
            pid = find_pid(n)
            if pid:
                os.kill(pid, signal.SIGKILL)
                print(f"[engine-manager] killed {n} (pid {pid})")
        return

    if cmd in ("start", "restart"):
        if not name:
            print("need an engine name")
            return
        cfg = ENGINES[name]
        need = cfg.get("mem_gb", 0)
        free = free_mem_gb()
        # Memory guard: don't OOM the box for a big on-demand model
        if need > 2.0 and free < need + 1.0:
            print(f"[engine-manager] WARNING: {name} needs ~{need:.0f}GB but "
                  f"only {free:.1f}GB free. Stop a big engine first or it may OOM.")
        if cmd == "restart":
            pid = find_pid(name)
            if pid:
                os.kill(pid, signal.SIGKILL)
                time.sleep(2)
        launch(name, port)
        wait_until_up(name, port or cfg["port"])
        return

    if cmd == "stop":
        if not name:
            print("need an engine name")
            return
        pid = find_pid(name)
        if pid:
            os.kill(pid, signal.SIGKILL)
            print(f"[engine-manager] killed {name} (pid {pid})")
        else:
            print(f"[engine-manager] {name} not running")
        return

    print(__doc__)


if __name__ == "__main__":
    main()
