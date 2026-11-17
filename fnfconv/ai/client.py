"""Minimal, dependency-free LLM client (Anthropic or any OpenAI-compatible server, e.g. Ollama/LM Studio)."""
from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path


class AIError(Exception):
    pass


class AIClient:
    def __init__(self, provider, model, base_url=None, api_key=None, cache_dir=None, timeout=180):
        self.provider, self.model, self.timeout = provider, model, timeout
        self.base_url = (base_url or ("https://api.anthropic.com" if provider == "anthropic" else "https://api.openai.com/v1")).rstrip("/")
        self.api_key = api_key
        self.cache = Path(cache_dir) if cache_dir else None
        if self.cache:
            self.cache.mkdir(parents=True, exist_ok=True)

    @classmethod
    def create(cls, provider="auto", model=None, base_url=None, cache_dir=None, api_key=None):
        if provider == "none":
            return None
        ak, ok = os.environ.get("ANTHROPIC_API_KEY"), os.environ.get("OPENAI_API_KEY")
        if api_key:
            if provider == "auto":
                provider = "anthropic" if api_key.startswith("sk-ant") else "openai"
            ak, ok = (api_key, ok) if provider == "anthropic" else (ak, api_key)
        if provider == "auto":
            provider = "anthropic" if ak else ("openai" if (ok or base_url) else "none")
            if provider == "none":
                return None
        if provider == "anthropic":
            if not ak:
                raise AIError("ANTHROPIC_API_KEY is not set")
            return cls("anthropic", model or os.environ.get("FNFCONV_MODEL", "claude-sonnet-5-5"), base_url, ak, cache_dir)
        if provider == "openai":
            model = model or os.environ.get("FNFCONV_MODEL")
            if not model:
                raise AIError("--model is required for the openai-compatible provider")
            return cls("openai", model, base_url, ok, cache_dir)
        raise AIError(f"unknown provider {provider}")

    def complete(self, system, user, max_tokens=8000):
        key = hashlib.sha256(json.dumps([self.provider, self.model, system, user]).encode()).hexdigest()
        cf = self.cache / f"{key}.txt" if self.cache else None
        if cf and cf.exists():
            return cf.read_text(encoding="utf-8")
        text = self._call(system, user, max_tokens)
        if cf:
            cf.write_text(text, encoding="utf-8")
        return text

    def _call(self, system, user, max_tokens):
        if self.provider == "anthropic":
            url = f"{self.base_url}/v1/messages"
            headers = {"x-api-key": self.api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
            body = {"model": self.model, "max_tokens": max_tokens, "system": system,
                    "messages": [{"role": "user", "content": user}]}
        else:
            url = f"{self.base_url}/chat/completions"
            headers = {"content-type": "application/json"}
            if self.api_key:
                headers["authorization"] = f"Bearer {self.api_key}"
            body = {"model": self.model, "max_tokens": max_tokens,
                    "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        data, last = json.dumps(body).encode(), None
        for attempt in range(3):
            req = urllib.request.Request(url, data=data, headers=headers, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    j = json.loads(r.read().decode("utf-8"))
                if self.provider == "anthropic":
                    return "".join(b.get("text", "") for b in j.get("content", []) if b.get("type") == "text")
                return j["choices"][0]["message"]["content"]
            except urllib.error.HTTPError as e:
                last = f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:300]}"
                if e.code not in (429, 500, 502, 503, 529):
                    break
            except (urllib.error.URLError, TimeoutError, KeyError, json.JSONDecodeError) as e:
                last = str(e)
            time.sleep(2 ** attempt)
        raise AIError(last or "unknown error")
