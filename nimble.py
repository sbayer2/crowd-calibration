"""Nimble (Bespoke Labs, 9B, Apache 2.0) over local Ollama's /v1/systemone: Jev's API, run on this Mac.

Same call shape as jev.ask: ask(state, questions) -> the parsed response plus `latency_s`. Nimble takes choice
criteria as {key: description}; Jev also accepts {key: {"what": description}}, so those are flattened here and the
questions stay byte-for-byte the same text. Temperature 0 (the model's Modelfile), so one run per question.
Requires `ollama pull nimble` and Ollama >= 0.40.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any

URL = "http://localhost:11434/v1/systemone"
MODEL = "nimble"


def _adapt(q: dict[str, Any]) -> dict[str, Any]:
    if q.get("type") == "choice" and isinstance(q.get("criteria"), dict):
        q = {**q, "criteria": {k: (v.get("what") if isinstance(v, dict) else v) for k, v in q["criteria"].items()}}
    return q


def ask(state: Any, questions: dict[str, Any], model: str = MODEL) -> dict[str, Any]:
    body = json.dumps({"model": model, "state": state, "questions": {k: _adapt(q) for k, q in questions.items()}}).encode()
    for attempt in range(1, 4):
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(urllib.request.Request(URL, data=body, headers={"Content-Type": "application/json"}),
                                        timeout=120) as r:
                out = json.load(r)
            out["latency_s"], out["attempts"] = round(time.perf_counter() - t0, 3), attempt
            return out
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"nimble HTTP {exc.code}: {exc.read()[:300].decode('utf-8', 'replace')}") from exc
        except (urllib.error.URLError, TimeoutError):
            if attempt == 3:
                raise
            time.sleep(2 * attempt)
    raise RuntimeError("unreachable")
