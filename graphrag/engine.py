#!/usr/bin/env python3
"""engine.py — on-demand engine manager for the sanctuary.

Usage:
  python3 engine.py list                # show running engines + memory
  python3 engine.py stop qwen           # stop Qwen 7B (precision)
  python3 engine.py stop gemma          # stop Huihui Gemma 4 (dream)
  python3 engine.py stop violet         # stop Violet Lotus 12B (dirty side)
  python3 engine.py start qwen [port]   # start an engine (default port 8080)
  python3 engine.py start gemma [port]  #   gemma -> 8082, violet -> 8084
  python3 engine.py start violet [port]
  python3 engine.py status              # same as list

On-demand model: load an engine only when needed, unload it after. Never run
all three at once (RAM: 15.1GB; Qwen maps ~9.4GB, Gemma ~12.4GB, Violet 8.7GB —
they don't coexist). Violet Lotus is SWAP-IN ONLY: start her alone.
"""
import os
import signal
import subprocess
import sys

VENV_PY = "/root/.llm-venv/bin/python3"
WORKSPACE = "/mnt/android/hermes-workspace"

ENGINES = {
    "qwen": {
        "model": f"{WORKSPACE}/Qwen2.5-Coder-7B-Instruct-abliterated-Q5_K_M.gguf",
        "port": 8080,
        "label": "Qwen 7B (precision)",
        "mode": "server",
    },
    "gemma2": {
        "model": f"{WORKSPACE}/gemma-2-9b-it-abliterated-Q4_K_M.gguf",
        "port": 8083,
        "label": "Gemma2 9B (set aside)",
        "mode": "direct",  # MUST use direct API — llama_cpp.server stalls on her
    },
    "violet": {
        "model": f"{WORKSPACE}/MN-Violet-Lotus-12B.IQ4_XS.gguf",
        "port": 8084,
        "label": "Violet Lotus 12B IQ4_XS (dirty side)",
        "mode": "server",
    },
    "router": {
        "model": f"{WORKSPACE}/qwen2.5-0.5b-instruct-q8_0.gguf",
        "port": 8085,
        "label": "Router 0.5B Q8_0 (routing/tagging)",
        "mode": "server",
    },
    "rerank": {
        "model": f"{WORKSPACE}/qwen3-reranker-0.6b-q8_0.gguf",
        "port": 8086,
        "label": "Reranker 0.6B Q8_0 (relevance scoring)",
        "mode": "server",
    },
}


def running_pids():
    """Find running llama_cpp server python processes by model name."""
    out = subprocess.run(
        ["pgrep", "-af", "llama_cpp.server"],
        capture_output=True, text=True,
    ).stdout
    found = {}
    for line in out.splitlines():
        if "llama_cpp.server" not in line:
            continue
        pid = int(line.split()[0])
        for name, cfg in ENGINES.items():
            if cfg["model"].split("/")[-1] in line:
                found[name] = pid
    return found


def engine_up(name):
    import urllib.request
    port = ENGINES[name]["port"]
    try:
        with urllib.request.urlopen(f"http://localhost:{port}/v1/models", timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


def stop(name):
    pids = running_pids()
    if name not in pids:
        print(f"{ENGINES[name]['label']}: not running")
        return
    pid = pids[name]
    os.kill(int(pid), signal.SIGTERM)
    print(f"{ENGINES[name]['label']}: stopping (pid {pid})")
    # also kill the parent bash wrapper
    try:
        parent = int(open(f"/proc/{pid}/stat").read().split()[3])
        os.kill(parent, signal.SIGTERM)
    except Exception:
        pass


def start(name, port=None):
    cfg = ENGINES[name]
    if engine_up(name):
        print(f"{cfg['label']}: already running on :{cfg['port']}")
        return
    port = port or cfg["port"]
    env = dict(os.environ)
    env["VIRTUAL_ENV"] = "/root/.llm-venv"
    env["PORT"] = str(port)

    # Gemma2 9B MUST use the direct-API loader (llama_cpp.server stalls on her:
    # builds the 1858-node graph then never binds the port). Verified path.
    if cfg.get("mode") == "direct":
        print(f"starting {cfg['label']} via DIRECT API on :{port} ...")
        subprocess.Popen(
            [VENV_PY, "/root/gemma2_direct.py"],
            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        print("  (direct API; give it ~30s for the 5.4GB model)")
        return

    cmd = [
        VENV_PY, "-m", "llama_cpp.server",
        "--model", cfg["model"],
        "--host", "0.0.0.0",
        "--port", str(port),
        "--n_ctx", "8192",
        "--n_threads", "4",
        "--n_gpu_layers", "0",
    ]
    # CPU-optimized flags for the heavy 12B (verified: use_mlock + flash_attn +
    # q8_0 KV cache). llama_cpp.server uses UNDERSCORE forms; KV type via
    # --kv_overrides (no --type-k/--type-v flag exists).
    if name == "violet":
        cmd += [
            "--use_mlock", "True",
            "--flash_attn", "True",
            "--kv_overrides", "general.kv_cache.type=q8_0",
        ]
    print(f"starting {cfg['label']} on :{port} ...")
    subprocess.Popen(cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print("  (started in background; give it ~60s for an 8.7GB model, ~30s for 5-7GB)")


def watchdog_qwen(max_stall_checks=3):
    """Detect a WEDGED Qwen (loaded but not answering) and restart her.

    Qwen hangs under sustained load — the process stays alive but stops
    responding (5s timeout, no reply). This probes /v1/models; if the port is
    bound but the process is dead-on-arrival or unresponsive for N checks, kill
    and restart. Returns True if a restart happened.
    """
    import urllib.request
    import urllib.error
    port = ENGINES["qwen"]["port"]
    # If not up at all, nothing to watch (she's simply not loaded)
    try:
        with urllib.request.urlopen(f"http://localhost:{port}/v1/models", timeout=2) as r:
            return False  # responding fine
    except Exception:
        pass
    # Port not answering: is the process even alive?
    pids = running_pids()
    if "qwen" not in pids:
        return False  # not running, nothing to restart
    # Process alive but unresponsive = wedged. Kill and restart.
    print(f"{ENGINES['qwen']['label']}: WEDGED (process alive, no response). Restarting...")
    stop("qwen")
    import time
    time.sleep(2)
    start("qwen")
    return True


def status():
    print(f"{'ENGINE':22s} {'PORT':6s} {'STATUS':10s} MEM")
    for name, cfg in ENGINES.items():
        up = engine_up(name)
        mem = ""
        pids = running_pids()
        if name in pids:
            try:
                for line in open(f"/proc/{pids[name]}/status"):
                    if line.startswith("VmSize:"):
                        mem = f"{int(line.split()[1])//1024} MB"
                        break
            except Exception:
                pass
        print(f"{cfg['label']:22s} :{cfg['port']:<5d} {'UP' if up else 'down':10s} {mem}")
    import subprocess as sp
    r = sp.run(["free", "-m"], capture_output=True, text=True).stdout
    print("\n" + "\n".join(r.splitlines()[1:3]))


def main():
    args = sys.argv[1:]
    if not args or args[0] in ("list", "status"):
        status()
    elif args[0] == "stop" and len(args) > 1:
        stop(args[1])
    elif args[0] == "start" and len(args) > 1:
        start(args[1], int(args[2]) if len(args) > 2 else None)
    elif args[0] == "watchdog":
        did = watchdog_qwen()
        print("qwen watchdog: restart" if did else "qwen watchdog: healthy")
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
