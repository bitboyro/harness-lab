# Proposal: Infrastructure error taxonomy and fail-fast

**Status:** **Adopted 2026-08-07** as [`decisions.md` G11](./decisions.md#g11--infrastructure-failures-are-void-not-data). Packages A, B and C all implemented. This file is now background reasoning; G11 is the durable record.  
**Date:** 2026-08-07  
**Companions:** [`running-the-experiment.md`](./running-the-experiment.md) · [`decisions.md`](./decisions.md) (G4 error *affordance* axis is unrelated) · [`harness-benchmark-spec.md`](./harness-benchmark-spec.md)

This is a design note for classifying and acting on **harness / provider / transport** failures. It does **not** change the G4 `error_detail` axis (API response affordances for the mock catalog). That axis measures whether better 4xx text helps the agent; this note is about when the *platform under the experiment* is broken.

Until adopted into `decisions.md` / `plan.md`, this file is the only place the taxonomy and fail-fast policy are specified.

---

## 1. Problem

Today the harness is **data-oriented, not recovery-oriented**: almost every exception is caught, stringified, and recorded so a matrix can finish. That is good for “one bad cell should not crash the process.” It is bad for:

- Burning the rest of a matrix on a dead API key or empty wallet
- Filling the ledger with undifferentiated `trace.error` strings (`AuthenticationError: …`, `TransportError: 429 from …`, `RuntimeError: …`)
- Confusing **experiment signal** (wrong tool args, wrong final text, mock 422) with **infra death** (auth, billing, disk full)
- MCP transport failures aborting a whole run while JSON-RPC tool errors become per-call results — inconsistent, and easy to misread in reports

There is no structured `error_kind`, almost no retry/backoff, and no matrix-level abort when continuing cannot produce valid data.

---

## 2. Hard rule

**Content wrong ≠ infra broken.**

If the LLM provider accepted the request and the MCP/HTTP/sandbox call returned a usable response envelope — including 4xx, `isError: true`, validation prose, “not found”, or a final answer that fails the grader — that is **experiment signal**. Fail-fast must never trigger on:

- Grader failures (wrong or incomplete answer text)
- Hedged / confident wrong answers
- Tool choice or argument mistakes
- Mock-API business errors shaped by `error_detail` (terse vs field-scoped)
- MCP tool **application** errors delivered inside a successful transport/JSON-RPC call
- Truncation (`max_turns`)
- Correct refusals and false positives on unanswerable tasks

**Litmus test for abort:** the next N cells have ~zero chance of producing a valid data point *for reasons outside the packaging arm under test*.

**Classifier inputs (safe):** exception type, HTTP status on the *transport*, provider SDK error `code` / `type` (e.g. OpenAI `insufficient_quota`), `errno` (`ENOSPC`), whether failure happened before a usable response body.

**Classifier inputs (unsafe for fail-fast):** final answer text, tool result text, grader `detail`, substring matches like “unauthorized” inside a payload.

---

## 3. Current behavior (as implemented)

### 3.1 End-to-end flow

```
LLM provider.submit()  ──exception──► AgentRunner.run  → trace.error  → grade FAIL → results.jsonl.error
         │
         └─success──► tool call ──► Executor.invoke() → Result{status, body, error}
                                              │
                                              └─► CallRecord → metrics (4xx / wasted / recovery)
```

| Layer | Location | Behavior today |
|---|---|---|
| Agent loop | `engine/loop.py` — `AgentRunner` | Broad `except Exception` → `trace.error = f"{type}: {e}"` |
| LLM adapter | `engine/providers/openai_provider.py` | Only adapts “unsupported parameter”; all else re-raised |
| MCP transport | `engine/mcp/transport.py` — `TransportError` | HTTP / timeout / unreachable → raise |
| MCP protocol | `engine/mcp/client.py` — `McpError` | JSON-RPC `"error"` → raise |
| Tool execution | `engine/executors.py` | `McpError` → `Result(500,…)`; `TransportError` **not** caught |
| Grader | `engine/grader.py` | `trace.error` → `Outcome.FAIL` (“run error: …”) |
| Persist | `engine/results.py` | `error=trace.error` on the ledger row |
| Matrix CLI | `cli.py` | Outer except prints `ERROR`; concurrency note only (“until rate limits bite”) |

### 3.2 What is already handled (narrowly)

1. **Provider unsupported sampling param** — drop param, one retry, record in config snapshot (`unsupported`).
2. **Missing API key env** — `RuntimeError` at client construction (becomes run error if it escapes into a cell).
3. **MCP auth env missing** — `TransportError` at transport construction.
4. **MCP JSON-RPC errors** — per-call `Result` with status 500.
5. **Sandbox timeout / non-zero exit** — per-call `Result.error`.
6. **Forbidden calls** — `GuardedExecutor` blocked result (not raised).
7. **Mock API validation shapes** — G4 `ErrorDetail` / `shape_error` (experiment axis, not infra).
8. **KeyboardInterrupt** — hard exit; partial ledger kept for `--resume`.

### 3.3 Gaps

1. No infra taxonomy — rate limit / quota / auth / network / disk are undifferentiated strings.
2. No retries/backoff for LLM or MCP transport failures.
3. `TransportError` is not a subclass of `McpError`; mid-run HTTP/network MCP failures abort the **run** instead of becoming a call `Result`.
4. MCP tool-level `isError` / embedded HTTP `status` is ignored by `McpToolCallExecutor` (always `status=200` on JSON-RPC success) — G4-style 4xx metrics under-count on MCP arms.
5. JSON-RPC faults become status **500**, which is outside `is_client_error` (400–499).
6. Report copy claims harness errors are “excluded from rates,” but grader marks them `fail` and analysis still counts them in `graded` (`NOT_GRADED` is only `truncated` / `ungraded`).
7. CLI outer except can lose a run from the ledger entirely (print only).
8. Disk / persistence failures are not special-cased; a full disk mid-matrix corrupts the “append-per-run” guarantee silently or messily.
9. Name collision: axis `error_detail` is API affordance, not classification of provider/MCP client errors.

---

## 4. Taxonomy

Errors are grouped by **layer**. Disposition (record / exclude / abort) is per layer, not per English phrasing of the message.

### Layer 0 — Experiment signal (never abort)

What the matrix is designed to measure.

| Kind | Examples |
|---|---|
| Wrong / incomplete answer | Final text fails gold / assertions |
| Bad tool use | Wrong tool, wrong args, redundant calls, forbidden attempt |
| Target API business errors | 400/404/422 validation; “series not found”; G4-shaped bodies |
| MCP tool application errors | JSON-RPC **success** with `isError` / structured 4xx; “invalid argument” in tool body |
| Abstention outcomes | Correct refusal; false positive on unanswerable |
| Truncation | Hit `max_turns` |
| Sandbox logic failure | Generated client surfaces HTTP error as data; script exits non-zero after a handled API error |

**Disposition:** normal `outcome` + call metrics. Count in packaging rates. Never fail-fast.

### Layer 1 — Operator / config (refuse to start)

Broken setup, not a measured arm.

| Kind | Examples |
|---|---|
| Missing credentials env | `OPENAI_API_KEY` unset; MCP auth env unset |
| Bad pack / plan | `PackError`, `ConfigError`, unknown preset, `BudgetNotApproved` |
| Missing deps | `openai` package not installed |
| Unknown model pricing | planner cannot price the run |
| Target unreachable at connect | MCP URL dead **before** any cell (preflight) |

**Disposition:** CLI exit before scheduling cells. Not a ledger “fail” row pretending to be packaging.

### Layer 2 — Fatal infra (fail-fast candidates)

Continuing wastes money or cannot persist trustworthy results.

| Kind | Examples | Why fatal |
|---|---|---|
| **Auth** | Provider 401 / invalid API key; MCP gateway 401/403 when auth is configured | Every next cell fails the same way |
| **Billing / quota** | `insufficient_quota`, billing hard limit, prepaid credit exhausted | Same |
| **Local persistence** | `ENOSPC` (disk full); permission denied writing `results.jsonl` / traces | Ledger/traces cannot be trusted |
| **Harness self-corruption** | Cannot append ledger under write lock; trace dir not writable | Same class as disk |
| **Systemic process limits** (optional) | Repeated OOM / ulimit across workers | Only after a threshold, not first occurrence |

**Disposition:** structured `error_kind`; abort remaining matrix work (or all remaining cells); keep `--resume` after the operator fixes the cause. Exclude from packaging success rates.

### Layer 3 — Transient infra (do not fail-fast by default)

| Kind | Examples |
|---|---|
| **Rate limit** | Provider 429 / TPM / RPM; some MCP gateways 429 |
| **Timeouts** | Provider or MCP socket timeout; sandbox `TimeoutExpired` |
| **Brief network** | DNS blip, connection reset, one-off “cannot reach” |
| **Provider overload** | LLM API 500/502/503 |
| **MCP transport flake** | Occasional non-JSON / empty SSE under load |

**Disposition:** record `error_kind`; optionally retry/backoff or soft-pause (separate package). Do not abort on first sight. Optional policy: sustained rate-limit for T minutes under low concurrency → soft-fatal (pause or abort-with-resume).

### Layer 4 — Target / arm infra (per-run or per-arm)

Something wrong with *this* packaging path or target process, not the LLM key.

| Kind | Examples | Suggested scope |
|---|---|---|
| MCP protocol / server bug | JSON-RPC `-32601`, failed `initialize`, malformed handshake | Fail run; optional fail-fast **that arm** if every cell dies identically |
| Tool list drift | Called tool missing from surface | Per-run or per-arm |
| Sandbox broken | Interpreter missing in jail; setup script failed | Per-arm |
| Shared mock API died | Experiment server crashed mid-matrix | Matrix-level if shared; arm-level if per-instance |
| Rig HTTP 5xx | Bug in our mock fixture | Usually per-run |

**Disposition:** structured kind; exclude from cross-arm packaging claims; optional arm-level abort. Rotating the provider API key will not fix these.

### Layer 5 — Ambiguous / unknown (never fail-fast)

| What you see | Easy misread | Safer rule |
|---|---|---|
| MCP body text “unauthorized” / “forbidden” | Looks like auth | If transport/JSON-RPC succeeded and this is tool/API payload → Layer 0 |
| Provider message contains “invalid” | Looks like bad args | Use SDK/HTTP status + error `code`/`type`, not prose |
| MCP HTTP 401 from gateway | Real auth | Layer 2 — classify from transport status |
| Tool structured `status: 401` | App policy | Layer 0 unless pack auth model says otherwise |
| Opaque `McpError` string | Anything | Prefer JSON-RPC `error.code` / HTTP status; else `unknown` |
| Grade fail “wrong text” | Never infra | Layer 0 always |

**Disposition:** `error_kind=unknown`; exclude from rates; **do not** abort. Prefer false negatives on abort over false positives.

---

## 5. Disposition matrix

| Layer | Record as | Count in packaging rates? | Abort? |
|---|---|---|---|
| 0 Experiment signal | Normal outcome / call metrics | Yes | No |
| 1 Config | CLI exit before runs | N/A | Don’t start |
| 2 Fatal infra | `error_kind=auth\|billing\|disk\|…` | No (separate bucket) | Yes — remaining matrix |
| 3 Transient | `error_kind=rate_limit\|timeout\|…` | Retry first if enabled; else infra bucket | No (unless sustained policy) |
| 4 Target/arm | Run or arm-level infra | Exclude from cross-arm claims | Optional arm-level |
| 5 Unknown | `error_kind=unknown` | Infra bucket | **No** |

---

## 6. Suggested `error_kind` enum

```text
experiment          # layer 0 — not an infra error (usually omitted / null)
config              # layer 1
auth                # layer 2
billing             # layer 2
disk                # layer 2  (ENOSPC, not writable)
rate_limit          # layer 3
timeout             # layer 3
network             # layer 3
provider_unavailable# layer 3 (provider 5xx / overload)
target_unavailable  # layer 4
protocol            # layer 4 (MCP/JSON-RPC structural)
unknown             # layer 5 — never fail-fast
```

### Ledger / trace fields (proposed)

| Field | Where | Notes |
|---|---|---|
| `error` | row + trace (existing) | Human-readable string; keep for grep |
| `error_kind` | row + trace (new) | Enum above; null when Layer 0 and no infra exception |
| `error_http_status` | optional | Transport or provider HTTP status when known |
| `error_provider_code` | optional | e.g. `insufficient_quota`, `invalid_api_key` |
| `error_fatal` | optional bool | Whether this cell triggered (or would trigger) fail-fast |

Reporting should gain an explicit **Infrastructure** section distinct from packaging outcomes. Harness errors must actually be excluded from success rates (fix the `NOT_GRADED` / `graded` mismatch called out in §3.3).

---

## 7. Options (implementation packages)

### Package A — Observe

- Classify exceptions into `error_kind`
- Fix MCP plumbing: catch `TransportError` in the executor → per-call `Result` (unless classified fatal auth/billing at matrix level)
- Map tool `isError` / embedded `status` onto `Result.status` so MCP arms feed 4xx metrics
- Fix analysis: infra / `error_kind` rows excluded from packaging rates; report copy matches code

**Gets you:** honest reports; no auto-recovery; no abort.

### Package B — Don’t waste money (recommended next after A)

Everything in A, plus:

- **Fail-fast** on first (or N) `auth` / `billing` / `disk` (and unwritable ledger)
- Clear CLI message: what failed, which `error_kind`, that `--resume` is safe after fix
- Optional **preflight**: tiny provider call + MCP `initialize` / `tools/list` before scheduling cells

**Gets you:** dead keys and full disks stop the matrix; wrong tool text never does.

### Package C — Survive load

Everything in B, plus:

- Capped exponential backoff on `rate_limit` / `timeout` / brief `network` (honor `Retry-After` when present)
- Or soft-pause the worker pool on sustained 429 when `--concurrency` > 1

**Gets you:** matrices tolerate shared-key pressure. Defer until concurrency actually hurts.

### Explicit non-goals for v1

- Retrying auth/billing
- Fail-fast on grader failures or tool payload text
- Treating G4 mock 4xx as infra
- Perfect classification of every opaque `McpError` string (those stay `unknown`)

---

## 8. Fail-fast policy (draft for Package B)

### Triggers (abort remaining work)

| Trigger | Count threshold (draft) | Scope |
|---|---|---|
| `auth` | 1 | Whole matrix |
| `billing` | 1 | Whole matrix |
| `disk` / ledger unwritable | 1 | Whole matrix (immediate) |
| `rate_limit` | not by default | Optional later: after K consecutive under concurrency=1 |
| `unknown` | never | — |
| Layer 0 | never | — |

### On abort

1. Cancel pending futures (same spirit as KeyboardInterrupt handling).
2. Do not join forever on in-flight provider calls if process exit is required; ledger append-under-lock remains the durability story.
3. Print: `error_kind`, sample message, cells completed / remaining, reminder to fix cause and `--resume`.
4. Exit non-zero with a dedicated code (proposed: distinguish from Ctrl-C’s 130).
5. ~~Already-written rows stay valid; aborted cells are simply absent (resume fills them).~~

   **Corrected 2026-08-07.** This assumption was false and it cost a matrix. Fail-fast is not instant: cells already in flight finish and *write infra rows*, and cells that die inside the agent loop were being written as `outcome=fail` all along. `matrix-40` ended with 28 such rows, and because `completed()` keyed on `(arm, task, repeat)` with no outcome filter, `--resume` would have preserved them permanently.

   An infra row is **void, not done**. `--resume` re-runs it and appends a superseding row; readers take the newest per cell. The ledger stays append-only and the original row remains as evidence.

### What must not trigger abort

- Any graded packaging failure
- MCP/HTTP **response bodies** that look like auth failures
- Single timeout / single 429
- Per-arm protocol weirdness on first occurrence (optional arm circuit-breaker is a separate knob)

---

## 9. Classification sketch (provider + MCP + disk)

Priority order when multiple signals exist: **errno / write failure → provider typed code → HTTP status on transport → exception type → unknown**.

| Signal | `error_kind` |
|---|---|
| `errno == ENOSPC` or explicit “No space left on device” on ledger/trace write | `disk` |
| Permission / read-only failure on results path | `disk` (or `config` if path never writable) |
| OpenAI-style `invalid_api_key` / 401 on provider | `auth` |
| `insufficient_quota` / billing hard limit | `billing` |
| Provider 429 | `rate_limit` |
| Provider 5xx | `provider_unavailable` |
| Provider timeout / connection error | `timeout` / `network` |
| MCP transport HTTP 401/403 with auth configured | `auth` |
| MCP transport HTTP 429 | `rate_limit` |
| MCP transport timeout / URLError | `timeout` / `network` |
| MCP JSON-RPC error after successful HTTP | `protocol` or map code; **not** auth from message text |
| Tool result `isError` / structured 4xx | Layer 0 (`experiment`); set `Result.status` accordingly |
| Anything else | `unknown` |

Missing env vars at startup remain Layer 1 (`config`) and should fail before the pool starts.

---

## 10. Relationship to G4 (`error_detail`)

| Concern | G4 axis | This proposal |
|---|---|---|
| Question | Do better API error messages help agents recover? | Is the harness/provider/disk still able to run the matrix? |
| Typical artifact | Mock 422 body shape | `error_kind=billing` abort |
| Metrics | `error_recovery_rate`, turns-to-first-productive-call | Infra section; excluded from packaging rates |
| Fail-fast? | Never | Only Layer 2 |

Do not overload the name `error` in docs or CLI without saying which layer. Prefer **“infra error”** vs **“API error affordance”** in user-facing copy.

---

## 11. Open questions (resolve before coding)

1. **Threshold N** — abort on first `auth`/`billing`, or require 2 identical kinds to reduce false positives from a single flaky gateway?
2. **Arm-level circuit breaker** — if every cell of one arm dies with `target_unavailable` / `protocol`, skip that arm’s remainder but continue others?
3. **Retry before classify-as-fatal** — should a single 401 be retried once (clock skew / transient gateway), or trusted immediately?
4. **Exit codes** — dedicated codes for auth vs billing vs disk vs generic infra abort?
5. **Field mode** — same taxonomy and fail-fast, or observe-only (Package A) for customer targets?
6. **Analysis break** — introduce `outcome=infra-error` (or keep `fail` + `error_kind` and fix `NOT_GRADED`)? Prefer an explicit outcome if it clarifies reports.
7. **Preflight cost** — one cheap completion + MCP initialize per matrix vs per arm vs skip when `--resume`?

---

## 12. Adoption checklist

- [x] Append a decision in `decisions.md` — [G11](./decisions.md#g11--infrastructure-failures-are-void-not-data)
- [x] Add `error_kind` (and optional status/code fields) to trace + ledger schema — `engine/infra.py`; `error_kind`, `error_http_status`, `error_provider_code`, `error_fatal`, `retries`
- [x] Implement classifier with unit tests for provider/MCP/disk fixtures — **including negative tests** that tool-body “unauthorized” does not become `auth` — `tests/test_infra_errors.py`
- [x] Fix `McpToolCallExecutor`: `TransportError` → `Result`; map `isError`/embedded status — also maps JSON-RPC codes into 400–499 (gap #5)
- [x] Fix analysis/reporting so infra rows are truly excluded from packaging rates — `outcome=infra-error` added to `NOT_GRADED`
- [x] Package B: matrix abort + message + `--resume` story + exit code (40)
- [x] Preflight — free-space check plus a one-completion provider check, default-on, `--no-preflight` to skip
- [x] Update `running-the-experiment.md` with infra abort / resume notes
- [x] Package C — capped jittered backoff on transient kinds, honouring `Retry-After`. Retry is **opt-in per call site** and deliberately off for `tools/call`; see G11 rule 3.

### What adoption changed in the numbers

Re-reading `matrix-40` with the 28 ENOSPC rows reclassified moved `D1 vs A1` from **−9.4% (p=0.60, n.s.)** to **+5.4% (p=0.031, significant)**. The sign of the effect was an artifact of counting a full disk as a packaging failure. D1 is still short 249 cells, so that figure is provisional until the matrix is resumed.

### Consequence for existing results: the 4xx metrics were structurally dead

Fixing gap #4 revealed that the flat `status=200` had pinned five metrics on every MCP arm. Across `matrix-40`, `argument_validity` is exactly `1.0` on all 690 runs of all six MCP arms — one distinct value — and `error_recovery_rate`, the **headline metric for the G4 affordance sweep**, is null on essentially every run. A sample of 250 MCP-arm traces found 4% contained a 4xx tool result (mostly 422) recorded as a success.

Also affected: `discovery_overhead`, `turns_to_first_productive_call`, `wasted_calls`.

The evidence survives — traces store the tool result body with its `isError` and embedded `status`, which is exactly the case for keeping full traces. These metrics can be recomputed from stored traces without re-running anything.

**Still open, and larger:** C1 (shell) and D1 (code) put a *process exit code* in `Result.status`, not an HTTP status, so their 4xx metrics are structurally unavailable too — and unlike the MCP arms, the HTTP status is buried in sandbox stdout rather than in a structured field. G4 cannot be answered on those arms until that is addressed. Not in this proposal's scope.
