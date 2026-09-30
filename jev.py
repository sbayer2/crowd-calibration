"""Jev over Vercel AI Gateway. Copied from safety-set/jev.py (the transport only; its safety-set summary was dropped).

The gateway serves the alias `typesafe-ai/jev` and cannot be pinned to a version (safety-set ADC-003), so answers can
drift between runs; the runner asks each market three times. Requests retry with backoff on 429 and 5xx.
"""

from __future__ import annotations

import json
import os
import random
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

URL = "https://ai-gateway.vercel.sh/typesafe/v1/systemone"
MODEL = "typesafe-ai/jev"
RETRY_STATUSES = frozenset({429, 500, 502, 503, 529})
MAX_ATTEMPTS = 7
BACKOFF_MAX = 20.0


class JevError(RuntimeError):
    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


def ask(state: dict[str, Any], questions: dict[str, Any], model: str = MODEL) -> dict[str, Any]:
    """One System One request. Returns the parsed response plus `latency_s`."""
    key = os.environ.get("AI_GATEWAY_API_KEY")
    if not key:
        raise JevError("AI_GATEWAY_API_KEY is not set (expected in .env)")
    body = json.dumps({"model": model, "state": state, "questions": questions}).encode()
    request = urllib.request.Request(URL, data=body, headers={
        "Authorization": f"Bearer {key}", "Content-Type": "application/json", "User-Agent": "crowd-calibration/0.1"})

    delay = 0.5
    for attempt in range(1, MAX_ATTEMPTS + 1):
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                out = json.load(response)
            out["latency_s"] = round(time.perf_counter() - started, 2)
            out["attempts"] = attempt
            return out
        except urllib.error.HTTPError as exc:
            detail = exc.read()[:300].decode("utf-8", "replace")
            if exc.code not in RETRY_STATUSES or attempt == MAX_ATTEMPTS:
                raise JevError(f"HTTP {exc.code}: {detail}", exc.code) from exc
            retry_after = exc.headers.get("retry-after")
            if retry_after and retry_after.replace(".", "", 1).isdigit():
                delay = min(float(retry_after), BACKOFF_MAX)
        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt == MAX_ATTEMPTS:
                raise JevError(f"unreachable: {exc}") from exc
        time.sleep(delay + random.uniform(0, 0.25 * delay))
        delay = min(delay * 2, BACKOFF_MAX)
    raise JevError("exhausted retries")

