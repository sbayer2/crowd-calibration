"""openjev (AlexWortega/openjev 4B v5, open Qwen3.5 NLI cross-encoder) asked the same two questions as Jev, on this Mac.

Pattern of safety-set/openjev_arm.py. The option texts ride in the adapter's rubric. Readout: each option's entailment
probability, normalised over the options; for the noul, P(yes) = ent(yes) / (ent(yes) + ent(no)). Deterministic and
independent of option order, so one run.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent / "vendor" / "openjev"))

from questions import BINS, NOUL_FALSE, NOUL_INSTR, NOUL_TRUE, SCORE_INSTR  # noqa: E402

REPO, REVISION, SUBFOLDER = "AlexWortega/openjev", "26de23c44b67586b4bea31c0ef2e016e3068ae66", "qwen3.5-4b-nli-v5"
_model = None


def _load():
    global _model
    if _model is None:
        from huggingface_hub import snapshot_download
        from openjev_decide import OpenJev
        local = snapshot_download(REPO, revision=REVISION, allow_patterns=[f"{SUBFOLDER}/*"], local_files_only=True)
        _model = OpenJev.from_pretrained(local, subfolder=SUBFOLDER, device=os.environ.get("OPENJEV_DEVICE", "mps"))
    return _model


def ask(st: dict[str, str]) -> tuple[float, list[float]]:
    """(P(yes), probabilities over BINS in order)."""
    from openjev_decide import RUBRIC_MARK
    labels = [str(i) for i in range(len(BINS))]
    qs = [{"type": "noul", "options": ["no", "yes"],
           "instructions": NOUL_INSTR + RUBRIC_MARK + json.dumps({"no": NOUL_FALSE, "yes": NOUL_TRUE})},
          {"type": "score", "options": labels,
           "instructions": SCORE_INSTR + RUBRIC_MARK + json.dumps({lb: text for lb, (text, _) in zip(labels, BINS)})}]
    noul, score = _load().decide(json.dumps(st, ensure_ascii=False), qs)
    return noul["noul"], [score["probabilities"][lb] for lb in labels]
