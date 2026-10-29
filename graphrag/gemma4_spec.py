#!/usr/bin/env python3
"""gemma4_spec.py - Gemma4 12B with N-GRAM SPECULATIVE DECODING + PROMPT CACHE.

No drafter model needed. Two levers inside the 12B's own KV cache:
  1. LlamaPromptLookupDecoding (n-gram lookup): reuses the 12B's OWN recent
     tokens as draft candidates - no external model, no tokenizer mismatch.
  2. LlamaCache (prompt caching): reuses KV across repeated/repeated-prefix
     prompts (our "good girl"-style triggers). Big win on our workload.

Tunable via env:
  ENABLE_NGRAM=1 (default) - n-gram spec decode
  ENABLE_CACHE=1 (default) - prompt cache (2GB default)
  NGRAM_N=2, NGRAM_PRED=10 - n-gram params

Serves OpenAI-compatible /v1/chat/completions on :8083.
"""
import os
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, "/root/.llm-venv/lib/python3.12/site-packages")

MODEL = "/mnt/android/hermes-workspace/Huihui-gemma-4-12B-it-abliterated.Q4_K_M.gguf"
PORT = int(os.environ.get("PORT", "8083"))
ENABLE_NGRAM = os.environ.get("ENABLE_NGRAM", "0") == "1"
ENABLE_CACHE = os.environ.get("ENABLE_CACHE", "1") == "1"
NGRAM_N = int(os.environ.get("NGRAM_N", "2"))
NGRAM_PRED = int(os.environ.get("NGRAM_PRED", "10"))
CACHE_SIZE = int(os.environ.get("CACHE_SIZE", str(2 * 1024 * 1024 * 1024)))  # 2GB

try:
    from llama_cpp import Llama, LlamaCache
    from llama_cpp.llama_speculative import LlamaPromptLookupDecoding

    kw = dict(
        model_path=MODEL,
        n_ctx=8192,
        n_threads=4,
        n_gpu_layers=0,
        use_mlock=True,
        flash_attn=True,
        type_k=8,
        type_v=8,
    )

    # Lever 1: n-gram speculative decoding (reuses the 12B's own tokens)
    if ENABLE_NGRAM:
        kw["draft_model"] = LlamaPromptLookupDecoding(
            max_ngram_size=NGRAM_N, num_pred_tokens=NGRAM_PRED
        )
        print(f"[gemma4-spec] n-gram spec decode ON (n={NGRAM_N}, pred={NGRAM_PRED})",
              flush=True)

    llm = Llama(**kw)

    # Lever 2: prompt cache / KV reuse
    if ENABLE_CACHE:
        cache = LlamaCache(capacity_bytes=CACHE_SIZE)
        llm.set_cache(cache)
        print(f"[gemma4-spec] prompt cache ON ({CACHE_SIZE//1024//1024}MB)", flush=True)

    print(f"[gemma4-spec] loaded {MODEL.split('/')[-1]} on :{PORT}", flush=True)
except Exception as e:
    print(f"[gemma4-spec] LOAD FAILED: {e}", flush=True)
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
    print(f"[gemma4-spec] serving on :{PORT}", flush=True)
    srv.serve_forever()
