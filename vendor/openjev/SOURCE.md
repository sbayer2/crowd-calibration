# Source: AlexWortega/openjev

Copied unmodified from https://huggingface.co/AlexWortega/openjev at revision
`26de23c44b67586b4bea31c0ef2e016e3068ae66` (2026-09-29). MIT licence (model card).

| file | path in the repo | sha256 |
|---|---|---|
| `openjev_decide.py` | `code/openjev_decide.py` | `c3db644745db0a756b7779ef0603e560adf2640f4fd12af3dd7fb2b28492609d` |
| `modeling_openjev.py` | `modeling_openjev.py` | `071670d0879963ee69600ed31f0f3d5a37bee314461709477e8ac0e25f33fd97` |

Weights: checkpoint `qwen3.5-4b-nli-v5/` at the same revision, loaded from the Hugging Face cache
(`Qwen3_5ForSequenceClassification`, 3-way NLI, bf16, 9.08 GB). Needs `torch` and `transformers>=5.17`.

`OpenJev.decide(state, questions)` scores each option as the entailment probability of a hypothesis built from the
instruction and the option, normalised over the options. For `noul`, P(yes) = ent(yes) / (ent(yes) + ent(no)). This
is not the same readout as the hosted Jev API.
