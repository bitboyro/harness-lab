# harness-ui skill materials (S5)

| File | Role |
|---|---|
| `SKILL.md` | **Authored** workflow — pre-registered in `provenance.json` |
| `generated-skill.md` | Mechanical index from OpenAPI — regenerate, do not hand-edit |
| `curl-reference.md` | curl examples from OpenAPI — regenerate, do not hand-edit |
| `openapi.snapshot.json` | Frozen `/v3/api-docs` for offline regeneration |
| `provenance.json` | `authored_commit` for V9 pre-registration |

## Regenerate

```bash
# Refresh snapshot when REST shapes change (from harness-ui/api):
UPDATE_SNAPSHOT=1 ./mvnw -Dtest=OpenApiSnapshotTest test

# Rewrite generated markdown from the snapshot:
python3 harness-ui/scripts/regenerate-skill-materials.py --write

# CI check (adapter test):
python3 -m pytest harness-ui/adapter/tests/test_skill_materials.py -q
```

Or pull live OpenAPI from a running server:

```bash
python3 harness-ui/scripts/regenerate-skill-materials.py --write \
  --url http://127.0.0.1:8085/v3/api-docs
```
