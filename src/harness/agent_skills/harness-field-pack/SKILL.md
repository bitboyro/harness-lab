---
name: harness-field-pack
description: >-
  Discover a customer's API or MCP, author a harness-lab field task pack,
  choose model/provider/arms, and advise on suite size for meaningful packaging
  results. Use when onboarding an API, creating packs/*.yaml, preparing a
  harness probe run or benchmark, picking --model, or asking what a good test
  suite looks like for harness-lab.
---

# Harness field pack (customer API → run)

Build everything needed for a **field** harness run: surface discovery, pack,
safety, model/params, arms, and suite quality. Do not invent metrics from
memory — quote lint/run/report output.

Canonical docs: `docs/test-your-api-harness.md`, `docs/design-your-test-run.md`,
`docs/reading-results.md`. For the install, the command ladder and what may be
claimed from a result, use the **harness-lab** skill.

## Workflow

Copy and track:

```
Field pack progress:
- [ ] 0. Confirm model + spend budget with the user
- [ ] 1. Discover surface (MCP / OpenAPI / both)
- [ ] 2. Scaffold a draft pack, then fill its TODOs with the user
- [ ] 3. Safety defaults + forbidden_calls
- [ ] 4. Lint (free)
- [ ] 5. Choose arms from what the surface unlocks
- [ ] 6. Probe cheap → read Z0 → resize suite if contaminated
- [ ] 7. Advise: what is / is not claimable at this n
```

## Commands

There is **no `harness probe`**. Field mode is `harness run --pack`, which is
the same execution path as the controlled matrix — so a field run gets the
ledger, `--concurrency`, `--resume`, `harness report`, `harness compare` and
`harness progress` too.

| Command | What it does |
|---|---|
| `harness lint <spec-or-url>` | T1 scorecard. Free, no key. `--demo` for the built-in API |
| `harness scaffold <url> -o packs/x.yaml` | Draft a pack from a live MCP server or OpenAPI doc |
| `harness init --agent both` | Install these skills into a user's project |
| `harness run --pack p.yaml --probe` | First contact: probe arms, 1 repeat, no resume |
| `harness run --pack p.yaml` | The full field run |
| `harness run --smoke` | ~12 runs against the rig; proves the install works |
| `harness run … --stream` | Print every message to/from the model as it happens |
| `harness transcript <trace>` | Replay a stored run: messages, calls, results |

Use `--stream --concurrency 1` when the user wants to *watch* one run. At higher
concurrency turns from different runs interleave.

---

## 0. Model and run params (required before spend)

**The pack does not set the model.** Model, provider, and sampling live on the
CLI (and env for pricing/keys). Always ask the user which model to use before
any run if they have not said.

### How to set it

```bash
harness run --pack packs/my-api.yaml --probe \
  --provider openai \
  --model gpt-5.6-luna \
  --reasoning-effort low \
  --temperature 0.0 \
  --caching off \
  --presets Z0 A1 A2 C1 D1 \
  --repeats 1
```

| Flag | Default | Notes |
|---|---|---|
| `--provider` | `openai` | Only `openai` is wired today |
| `--model` | `gpt-5.6-luna` | **Must** be priced — see below. Also available: `gpt-5.6-terra` / `gpt-5.6-sol` |
| `--reasoning-effort` | `low` | Always sent explicitly |
| `--temperature` | `0.0` | Dropped if the model rejects it; omission recorded |
| `--caching` | `off` | `on` or `list-cacheable` |
| `--max-turns` | `12` | Hit = truncation, not wrong answer |
| `--mcp-revision` | varies by command | `auto` / `2026-07-28` / `legacy`; never pool across revisions |

Same `--model` / `--provider` pattern on `harness rig` for controlled/matrix runs.

### Pricing gate

Harness refuses unknown models (no guessing in front of spend approval).

Built-in catalogue (`src/harness/engine/pricing.py`): `gpt-5.6-luna`,
`gpt-5.6-terra`, `gpt-5.6-sol` (and dated snapshots `model-YYYY-MM-DD`).

Override / add a model in `.env`:

```bash
# USD per million tokens: input,cached,cache-write,output
# (or in,out — or 8 values for short then long context)
echo 'HARNESS_PRICE_GPT_5_MINI=0.25,0.025,0.3125,2.00' >> .env
```

Env key = `HARNESS_PRICE_` + model uppercased with non-alnum → `_`.

Provider auth: `OPENAI_API_KEY` (optional `OPENAI_BASE_URL`). Target API tokens
via names in the pack (`api.auth.env`), never inlined.

### Advise the customer

- Results are **stamped to that model version** — not “APIs in general”.
- Cheaper tier (`luna`) for discovery probes; stronger tier only when the claim
  matters and budget allows.
- Do not change `--model` mid-comparison and then rank arms across those runs.

Record the chosen model in the handoff (manifest will also store it).

---

## 1. Discover the surface

Gather from the customer / their repos (do not invent endpoints):

| Need | Why |
|---|---|
| MCP URL and/or OpenAPI URL/path | Unlocks arms |
| HTTP base URL + `base_url_env` | Required for C*/D* |
| Auth scheme | `none` / `bearer` / `header` / `basic` + env var name |
| Read vs write ops | Default read-only |
| Destructive / irreversible ops | `forbidden_calls` |
| Staging vs prod | Staging for anything beyond read probe |

**Arm unlock map**

| Surface | Arms |
|---|---|
| Nothing special | Z0 |
| MCP | A1, A2, B1, B2, E1 (+ M1 only if writes/confirm matter) |
| Authored skill at `skills/{spec-title-slug}.md` | B1-auth, B2-auth, D2-auth |
| OpenAPI with real HTTP method/path + reachable base | C1, C2, D1, D2 |
| Gold `gold_call_sequence` on read tasks | Z1 |
| Field pack without HTTP `_meta` | Skip D3 |
| D4 | Not implemented — never promise |

MCP-only packs: do **not** run C/D expecting magic — synthetic `/{tool}` paths
are useless unless HTTP serves them. Prefer MCP REST twin OpenAPI when both
exist (e.g. `https://mcp.aipolicies.eu/v3/api-docs`).

---

## 2. Safety (before live traffic)

In every field pack:

```yaml
pack:
  report_class: field          # mandatory; never pool with controlled
safety:
  writes_enabled: false        # default; keep until staging + isolation exist
  forbidden_calls: [...]       # every destructive op; this IS the field harm signal
isolation:
  mode: none                   # reads
```

Writes: staging + `isolation` + `state_snapshot`; grade with `state-diff`, never
transcript. Prod-looking writes need `production_ack: true` **and**
`--i-know-this-is-production`. Advise against for first runs.

---

## 3. Lint (free)

```bash
harness lint path/to/openapi.json
# or MCP-derived surface per docs
```

Findings are **hypotheses** (`?`), not measured effect sizes. Turn high-severity
items into tasks (unbounded lists, silent empty, ambiguous mutations).

---

## 4. Author the pack

**Start with `harness scaffold`, never a blank file:**

```bash
harness scaffold https://their-server/mcp --id their-api -o packs/their-api.yaml
```

It derives the surface, writes one stub per read operation, pre-fills
`forbidden_calls` with every operation it will not exercise, sets
`report_class: field` and `writes_enabled: false`, and adds ~15% unanswerable
slots. **Nothing is graded** — every task carries a `TODO` prompt and an empty
`grade`. That is deliberate: a stub that asserted something plausible would look
finished. Your job with the user is filling those in.

Pack describes **API + tasks only** — never names variants/arms.

### Meaningful suite shape

| Property | Target |
|---|---|
| Distinct tasks/cores | ≥20 to rank arms; ~40 for serious contrasts |
| Unanswerable | ~15% (`answerable: false` + `unanswerable_because`) |
| Answer locus | Data in *their* system / fresh IDs — not public training recall |
| Grades | Deterministic: `equals` / `contains` / `regex` / `jsonpath` / `script` |
| Difficulty mix | 1-hop + multi-hop + ambiguous |
| `gold_call_sequence` | Optional; unlocks selection accuracy + Z1 |
| Repeats | Power from **more tasks**, not more repeats of the same |

**Weak:** 5 public FAQ prompts, no unanswerables, no Z0, crown a winner on 1
repeat.  
**Strong:** ≥20 private cores, ~15% unanswerable, Z0 always run, forbidden
calls, grades on facts, n large enough that report MDE does not kill every
contrast.

If Z0 succeeds highly: **rewrite tasks** toward tenant-specific / non-public
answers. Do not “fix” packaging.

Minimal task sketch:

```yaml
tasks:
  - id: find-x
    prompt: "…"
    class: R
    answerable: true
    grade:
      - { type: contains, target: answer, value: "…" }

  - id: no-such-thing
    prompt: "…"
    class: R
    answerable: false
    unanswerable_because: "…"
```

---

## 5. Choose presets

| Customer has | First probe presets |
|---|---|
| MCP only | `Z0 A1 A2` then `B1-auth` if skill exists |
| HTTP + OpenAPI only | `Z0 C1` then `D1` |
| Both | `Z0 A1 A2 B1-auth C1` (+ `D1` optional) |

Always include **Z0**. Controls never “win” as shippable packaging.

---

## 6. Run ladder

1. **Lint** — free  
2. **Probe** — cheap, `--repeats 1`, small task set → crashes, fabrication, cost, Z0  
3. **Benchmark** — ≥20 graded cores when claiming lift / a winner  

```bash
harness run --pack packs/my-api.yaml --probe \
  --out results/<id> --id <id> \
  --model <agreed-model> \
  --presets Z0 A1 A2 C1 D1
```

Then: `harness report results/<id> --html report.html --charts charts/`

Read traces before believing any arm at ~0%.

---

## 7. What to tell the customer

1. Model used, pricing source, and that results are model-bound.  
2. Z0 rate — contamination measured, not removed; report **lift over Z0**.  
3. Whether n clears MDE; refuse to pick a winner if lead is noise or worsens
   harm/fabrication vs runner-up.  
4. Which arms were valid for *their* surface (and which were skipped and why).  
5. Field metrics are unvalidated vs the controlled rig — stamped `field`.  
6. Next step: more private cores / unanswerables / staging writes — not more
   repeats of the same five prompts.

### Best-params cheat sheet

| Goal | Advise |
|---|---|
| First contact | Cheap model, Z0 + 2–4 arms, 1 repeat, small suite |
| Ship packaging choice | ≥20 cores, Z0 always, lead > MDE, check abstention/harm |
| Safety ranking | `--weights harm=1` (or raise abstention/harm); keep ~15% unanswerable |
| High Z0 | Fix the suite, don’t oversell MCP/docs |

---

## Handoff checklist

Before calling the job done, confirm:

- [ ] User agreed `--model` / `--provider` / budget  
- [ ] Model is in catalogue or `HARNESS_PRICE_*` is set  
- [ ] Pack `report_class: field`, read-only unless staging writes agreed  
- [ ] Arms match MCP and/or OpenAPI+base URL  
- [ ] Authored skill path correct if using `*-auth`  
- [ ] ~15% unanswerables; grades deterministic  
- [ ] Z0 included in the run plan  
- [ ] Caveats stated (MDE, field, model-bound, contamination)
