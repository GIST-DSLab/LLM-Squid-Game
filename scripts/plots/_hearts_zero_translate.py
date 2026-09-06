"""Machine-translate recorded model output to Korean, with an on-disk cache.

READING AID ONLY, and the one thing in this report that is *not* recorded data:
the model's chain of thought and its answer were produced in English and are the
measurement. The Korean rendering exists so the note is readable, is labelled as
a machine translation everywhere it appears, and never replaces the English in
the stored run — the EN tab always shows the recorded bytes.

Translations are cached in ``<run>/translations.json`` keyed by a hash of the
source text, so rebuilding the page costs nothing and a re-run only translates
what is new.
"""

from __future__ import annotations

import hashlib
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import httpx

SYSTEM = (
    "You are a translator. Translate the user's text into natural Korean. "
    "It is a language model's reasoning transcript from a research experiment: "
    "keep every field name, number, and English identifier "
    "(P_THREAT, CHOICE, CONTINUE, FORFEIT, REASON, THREATENED, INTENSITY, "
    "BASIS, helpfulness, hz_0000-style ids) exactly as written. "
    "Translate nothing else into English. Preserve the line structure. "
    "Output the translation only, with no preamble and no commentary."
)


def _key(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


class Translator:
    def __init__(
        self,
        cache_path: Path,
        *,
        model: str = "gemma4:cloud",
        base_url: str = "http://localhost:11434",
        workers: int = 5,
        timeout: float = 240.0,
    ) -> None:
        self._path = cache_path
        self._model = model
        self._url = base_url.rstrip("/") + "/api/chat"
        self._workers = workers
        self._client = httpx.Client(timeout=timeout)
        self._lock = threading.Lock()
        self._cache: dict[str, str] = {}
        if cache_path.exists():
            self._cache = json.loads(cache_path.read_text(encoding="utf-8"))

    def _translate_one(self, text: str) -> str:
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": text},
            ],
            "stream": False,
            "think": False,
            "options": {"temperature": 0.2},
        }
        try:
            resp = self._client.post(self._url, json=payload)
            resp.raise_for_status()
            return (resp.json().get("message") or {}).get("content") or ""
        except Exception as exc:  # noqa: BLE001 - a failed translation is not fatal
            return f"[번역 실패: {type(exc).__name__}] 원문은 EN 탭에서 볼 것."

    def warm(self, texts: list[str]) -> None:
        """Translate everything not already cached, in parallel, then persist."""
        todo = [
            t
            for t in sorted({s.strip() for s in texts if s and s.strip()})
            if _key(t) not in self._cache
        ]
        if not todo:
            return
        print(f"  translating {len(todo)} new text(s) -> {self._path.name}")

        def run(text: str) -> None:
            out = self._translate_one(text)
            with self._lock:
                self._cache[_key(text)] = out

        with ThreadPoolExecutor(max_workers=self._workers) as pool:
            list(pool.map(run, todo))
        self.save()

    def get(self, text: str) -> str | None:
        if not text or not text.strip():
            return None
        return self._cache.get(_key(text.strip()))

    def save(self) -> None:
        self._path.write_text(
            json.dumps(self._cache, ensure_ascii=False, indent=1), encoding="utf-8"
        )
