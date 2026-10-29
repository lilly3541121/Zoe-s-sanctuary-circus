#!/usr/bin/env python3
"""gemma4_direct.py - Gemma4 12B abliterated (Huihui) deep storyteller.

Replaces Gemma2 9B. Same direct-Llama API pattern (llama_cpp.server stalls on
these models). Serves OpenAI-compatible /v1/chat/completions on :8083.

NOTE: 12B is ~6.9GB Q4_K_M, ~2.1x deeper than the 9B. Uses the KleidiAI native
build. Expect ~1.5-2.5 w/s (slower than the 9B but DEEPER, smarter).
"""
import os
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, "/root/.llm-venv/lib/python3.12/site-packages")

MODEL = "/mnt/android/hermes-workspace/Huihui-gemma-4-12B-it-abliterated.Q4_K_M.gguf"
PORT = int(os.environ.get("PORT", "8083"))

try:
    from llama_cpp import Llama
    llm = Llama(
        model_path=MODEL,
        n_ctx=8192,
        n_threads=4,
        n_gpu_layers=0,
        use_mlock=True,
        flash_attn=True,
        type_k=8,
        type_v=8,
    )
    print(f"[gemma4-direct] loaded {MODEL.split('/')[-1]} on :{PORT}", flush=True)
except Exception as e:
    print(f"[gemma4-direct] LOAD FAILED: {e}", flush=True)
    sys.exit(1)

_lock = threading.Lock()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/v1/models"):
            self._send(200, {"object": "list", "data": [{"id": "gemma4-12b", "object": "model"}]})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        if not self.path.startswith("/v1/chat/completions"):
            self._send(404, {"error": "not found"})
            return
        try:
            n = int(self.headers.get("Content-Length", "0"))
            req = json.loads(self.rfile.read(n))
        except Exception as e:
            self._send(400, {"error": str(e)})
            return

        messages = req.get("messages", [])
        max_tokens = int(req.get("max_tokens", 700))
        temperature = float(req.get("temperature", 0.8))

        prompt = ""
        for m in messages:
            role = m.get("role", "user")
            content = m.get("content", "")
            if role == "system":
                prompt += f"<|system|>\n{content}\n"
            elif role == "assistant":
                prompt += f"<|model|>\n{content}\n"
            else:
                prompt += f"<|user|>\n{content}\n"
        prompt += "<|model|>\n"

        try:
            with _lock:
                out = llm(
                    prompt,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    stop=["<|end|>", "<|user|>", "user"],
                )
            text = out["choices"][0]["text"].strip()
            for tok in ("<|end|>", "<|user|>", "<|model|>"):
                text = text.replace(tok, "")
            self._send(200, {
                "choices": [{"message": {"role": "assistant", "content": text}}],
                "usage": {"total_tokens": len(text.split())},
            })
        except Exception as e:
            self._send(500, {"error": str(e)})


if __name__ == "__main__":
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"[gemma4-direct] serving on :{PORT}", flush=True)
    srv.serve_forever()
