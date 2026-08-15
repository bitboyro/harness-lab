# harness-ui self-benchmark pack (T7.1)

Field-mode tasks against the harness-ui MCP surface. **Read-only** — every
mutating capability is listed in `forbidden_calls`, including `start_run` and
`start_experiment_run`.

## Validate

```bash
python harness-ui/adapter/harness_json.py pack-validate harness-ui/benchmark/harness-ui-self.yaml
```

## Probe (T7.2 — dry-run / Z0 floor)

With the API on loopback and the harness venv active:

```bash
export TARGET_BASE_URL=http://127.0.0.1:8085
harness run --pack harness-ui/benchmark/harness-ui-self.yaml \
  --presets Z0 --probe --yes --out /tmp/harness-ui-z0-probe
```

Copy key gold-free metrics from the probe report into `z0-floor.json` (template
provided). Z0 is the packaging floor — compare MCP arms as lift over this row.

## MCP URL

Pack targets `http://127.0.0.1:8085/mcp` (JSON-RPC `tools/list` + `tools/call`).
