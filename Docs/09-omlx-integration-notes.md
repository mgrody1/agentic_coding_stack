# oMLX Integration Notes

These notes are based on inspection of the uploaded oMLX repo snapshot.

## Relevant integration facts

The uploaded repo includes:
- `omlx/server.py`
- `omlx/model_settings.py`
- `omlx/model_profiles.py`
- `omlx/turboquant_kv.py`
- cache handling under `omlx/cache/`
- admin templates for TurboQuant model settings

This suggests the conductor should treat oMLX as an HTTP-serving runtime with model-level settings rather than trying to embed orchestration logic inside the runtime.

## Integration guidance

- use oMLX aliases externally in the conductor config
- keep TurboQuant settings model-local
- keep frontier planning outside the oMLX process
- use embeddings and rerank from oMLX as infrastructure for memory retrieval
- do not fork oMLX for the planner unless there is a later, very specific need

## Why this matters

The safest architecture boundary is:
- oMLX = inference + retrieval substrate
- frontier-dev = planning + orchestration + memory policy
