# Adapter — harness → JSON

The **only** place that imports harness internals. Subcommands mirror the
schemas in `schemas/` (frozen by S0). See `../docs/contracts.md`.

```bash
# from repo root, with harness installed
python3 harness-ui/adapter/harness_json.py report results/auth-smoke
python3 harness-ui/adapter/harness_json.py progress results/auth-smoke
python3 harness-ui/adapter/harness_json.py lint examples/openapi.json
python3 harness-ui/adapter/harness_json.py pack-validate examples/plan.yaml
```
