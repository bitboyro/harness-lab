import type {
  AdapterAnalysis,
  AdapterLint,
  AdapterReport,
  ArtifactRef,
  CellRef,
  CompareResult,
  CostProjection,
  CreateExperimentFromGenerateRequest,
  ExperimentRef,
  GenerateJob,
  GenerateManifestPayload,
  GenerateProgress,
  PackBody,
  PackRef,
  PackValidate,
  PackWriteResult,
  ProgressEnvelope,
  RunJob,
  RunRequest,
  RunSummary,
  StartGenerateRequest,
  Target,
  TranscriptResponse,
  LlmConfig,
  ProviderView,
  UpsertModelRequest,
  UpsertProviderRequest,
} from "./types";

const NOW = "2026-08-08T12:00:00.000Z";

export const MOCK_TARGETS: Target[] = [
  {
    id: "demo-openapi",
    kind: "openapi",
    label: "demo-catalog.json",
    createdAt: NOW,
  },
  {
    id: "demo-mcp",
    kind: "mcp",
    label: "http://127.0.0.1:8765/mcp",
    createdAt: NOW,
  },
];

const PACK_YAML: Record<string, string> = {
  demo: `id: demo
tasks:
  - id: t1
    prompt: "List titles"
`,
};

let runTick = 0;
const jobs = new Map<string, RunJob>();

export function mockListTargets(): Target[] {
  return [...MOCK_TARGETS];
}

export function mockUploadTarget(label: string, kind: "openapi" | "mcp"): Target {
  const t: Target = {
    id: `target-${MOCK_TARGETS.length + 1}`,
    kind,
    label,
    createdAt: new Date().toISOString(),
  };
  MOCK_TARGETS.unshift(t);
  return t;
}

export function mockLint(id: string): AdapterLint {
  void id;
  return {
    harness_version: "0.0.1",
    spec_path: "targets/demo-openapi/spec.json",
    findings: [
      {
        rule_id: "L1",
        severity: "medium",
        confidence: "heuristic",
        message: "Operation lacks a summary suitable for tool naming.",
        location: "paths./items.get",
      },
      {
        rule_id: "L4",
        severity: "low",
        confidence: "measured",
        message: "Enum values are documented.",
        location: null,
      },
    ],
    rules_run: 12,
    rules_measured: 4,
    measured_fraction: 4 / 12,
    footer:
      "4/12 rules measured · validation=heuristic · see harness lint --help",
  };
}

export function mockReadPack(id: string): PackBody {
  return {
    id,
    yaml: PACK_YAML[id] ?? `id: ${id}\ntasks: []\n`,
  };
}

export function mockListPacks(): PackRef[] {
  return [
    { id: "demo", path: "packs/demo.yaml", valid: true, error: null },
    { id: "demo-pack", path: "packs/demo-pack.yaml", valid: true, error: null },
  ];
}

export function mockWritePack(id: string, yaml: string): PackWriteResult {
  const bad = yaml.includes("INVALID") || !yaml.includes("id:");
  if (bad) {
    return {
      id,
      valid: false,
      error:
        "PackError: missing required field 'id' at document root (pack.py:142)",
    };
  }
  PACK_YAML[id] = yaml;
  return { id, valid: true, error: null };
}

export function mockValidatePack(id: string): PackValidate {
  const yaml = PACK_YAML[id] ?? "";
  const bad = yaml.includes("INVALID") || !yaml.includes("id:");
  if (bad) {
    return {
      harness_version: "0.0.1",
      path: `packs/${id}.yaml`,
      valid: false,
      error:
        "PackError: missing required field 'id' at document root (pack.py:142)",
      pack_id: id,
      task_count: null,
    };
  }
  return {
    harness_version: "0.0.1",
    path: `packs/${id}.yaml`,
    valid: true,
    error: null,
    pack_id: id,
    task_count: 1,
  };
}

export function mockProject(req: RunRequest): CostProjection {
  void req;
  return {
    projectionText:
      "Projected cost ≈ $0.12  (smoke · 2 presets · 1 repeat)\nMissing: (none)",
    exitCode: 1,
    stderrNames: [],
  };
}

export function mockStartRun(req: RunRequest): RunJob {
  const job: RunJob = {
    id: req.id,
    status: "running",
    pid: 4242,
    exitCode: null,
    outDir: `/data/results/${req.id}`,
    startedAt: new Date().toISOString(),
    finishedAt: null,
    errorKind: null,
    message: null,
  };
  jobs.set(req.id, job);
  runTick = 0;
  return job;
}

export function mockListRuns(): RunSummary[] {
  const fromJobs = [...jobs.values()].map((j) => ({
    id: j.id,
    status: j.status,
    startedAt: j.startedAt,
    finishedAt: j.finishedAt,
    message: j.message,
    model: "gpt-4.1-mini",
  }));
  if (fromJobs.length === 0) {
    return [
      {
        id: "smoke-demo",
        status: "succeeded",
        model: "gpt-4.1-mini",
        startedAt: NOW,
        finishedAt: NOW,
      },
    ];
  }
  return fromJobs;
}

export function mockProgress(id: string): ProgressEnvelope {
  const job =
    jobs.get(id) ??
    ({
      id,
      status: "succeeded" as const,
      pid: null,
      exitCode: 0,
      outDir: `/data/results/${id}`,
      startedAt: NOW,
      finishedAt: NOW,
      errorKind: null,
      message: null,
    } satisfies RunJob);

  if (job.status === "running") {
    runTick += 1;
    const done = Math.min(runTick, 4);
    const terminal = done >= 4;
    if (terminal) {
      job.status = "succeeded";
      job.exitCode = 0;
      job.finishedAt = new Date().toISOString();
      jobs.set(id, job);
    }
    return {
      job: { ...job },
      progress: {
        harness_version: "0.0.1",
        done,
        expected: 4,
        fraction: done / 4,
        eta_seconds: terminal ? 0 : (4 - done) * 2,
        elapsed_seconds: done * 2,
        started_at: job.startedAt,
        by_arm: { A1: Math.min(done, 2), Z0: Math.max(0, done - 2) },
        outcomes: { ok: done, error: 0 },
      },
      terminal,
    };
  }

  return {
    job: { ...job },
    progress: {
      harness_version: "0.0.1",
      done: 4,
      expected: 4,
      fraction: 1,
      eta_seconds: 0,
      elapsed_seconds: 12,
      started_at: job.startedAt,
      by_arm: { A1: 2, Z0: 2 },
      outcomes: { ok: 4, error: 0 },
    },
    terminal: true,
  };
}

export function mockReport(id: string): AdapterReport {
  return {
    harness_version: "0.0.1",
    run: {
      id,
      model: "gpt-4.1-mini",
      provider: "openai",
      report_class: "controlled",
      n_rows: 4,
      pooling_refused: false,
      presets: ["A1", "Z0"],
    },
    verdict: {
      winner: "A1",
      leader: "A1",
      runner_up: "Z0",
      reason: "A1 leads on composite score within MDE.",
      scores: { A1: 0.82, Z0: 0.1 },
      caveats: ["Smoke matrix — not powered for confirmatory claims."],
    },
    arms: {
      A1: {
        arm: "A1",
        name: "eager MCP",
        is_control: false,
        n: 2,
        graded: 2,
        success_rate: 1,
        harm_rate: 0,
        composite_score: 0.82,
        cost_per_success_usd: 0.03,
        lift: 0.7,
        below_mde: false,
      },
      Z0: {
        arm: "Z0",
        name: "no tools",
        is_control: true,
        n: 2,
        graded: 2,
        success_rate: 0,
        harm_rate: 0,
        composite_score: 0.1,
        cost_per_success_usd: null,
        lift: null,
        below_mde: true,
      },
    },
    validation: "validated-controlled",
  };
}

export function mockAnalysis(id: string, only?: string): AdapterAnalysis {
  void only;
  return {
    harness_version: "0.0.1",
    run: { id, model: "gpt-4.1-mini", report_class: "controlled" },
    generated_from: `results/${id}`,
    sections: {
      identity: {
        title: "Run identity",
        headers: ["field", "value"],
        rows: [
          { field: "id", value: id },
          { field: "model", value: "gpt-4.1-mini" },
        ],
      },
      standings: {
        title: "Standings",
        headers: ["arm", "success", "score"],
        rows: [
          { arm: "A1", success: 1, score: 0.82 },
          { arm: "Z0", success: 0, score: 0.1 },
        ],
      },
    },
  };
}

export function mockArtifacts(id: string): ArtifactRef[] {
  void id;
  return [
    {
      name: "report.html",
      path: "artifacts/report.html",
      contentType: "text/html",
      sizeBytes: 2048,
    },
    {
      name: "summary.json",
      path: "artifacts/summary.json",
      contentType: "application/json",
      sizeBytes: 512,
    },
  ];
}

export function mockListCells(id: string): CellRef[] {
  void id;
  return [
    {
      arm: "Z0",
      taskId: "core-000-W-safe",
      repeat: 0,
      outcome: "fail",
      turns: 1,
      calls: 0,
    },
    {
      arm: "A1",
      taskId: "core-000-W-safe",
      repeat: 0,
      outcome: "pass",
      turns: 3,
      calls: 2,
    },
  ];
}

export function mockTranscript(
  id: string,
  arm: string,
  taskId: string,
  repeat: number,
  verbose = false,
): TranscriptResponse {
  void id;
  void repeat;
  if (verbose) {
    return {
      text: `┌─ mock-trace  ·  ${taskId}  ·  ${arm}
  system   Answer the task using the tools available. You may call tools by name.
           Pack surface: list_episodes, get_episode, search_titles (mock).
── turn 0  ·  111↑  46↓  ·  2.1s
  user     Example task prompt for mock mode.
  ★ FINAL ANSWER: done
└─ done   (1 turn, 0 calls)
`,
    };
  }
  return {
    text: `┌─ mock-trace  ·  ${taskId}  ·  ${arm}
── turn 0  ·  111↑  46↓  ·  2.1s
  system   [task preamble]
  user     Example task prompt for mock mode.
  ★ FINAL ANSWER: done
└─ done   (1 turn, 0 calls)
`,
  };
}

export function mockCompare(runIds: string[]): CompareResult {
  const refuse = runIds.some((id) => id.includes("refuse") || id.includes("other-model"));
  if (refuse) {
    return {
      refused: true,
      refusalText:
        "REFUSING TO POOL\n\nBroken boundary: model\n  run smoke-demo: gpt-4.1-mini\n  run other-model: gpt-4o\n\nNever pool across model, mcp_revision, skill condition, or report class.",
      brokenBoundary: "model",
      artifactDir: null,
      stdout: "",
    };
  }
  return {
    refused: false,
    refusalText: null,
    brokenBoundary: null,
    artifactDir: "compare/c1/artifacts",
    stdout: "compare ok · setup deltas: repeats\nA1 lift stable across runs",
  };
}

export function mockListExperiments(): import("./types").ExperimentSummary[] {
  return [
    {
      id: "baseline-experiment-80",
      status: "draft",
      hasLedger: false,
      coverageFraction: 0,
      model: "gpt-5.6-luna",
      updatedAt: NOW,
    },
  ];
}

export function mockGetExperiment(id: string): import("./types").ExperimentEnvelope {
  return {
    harness_version: "0.0.1",
    schema_version: 1,
    experiment: {
      id,
      status: "draft",
      run_plan: {
        include: { presets: ["Z0", "A1", "A2"] },
        tasks: { generate: { cores: 80, seed: 1 } },
      },
      slices: {
        smoke: { description: "pipeline check", arms: ["A1", "A2"], cores: 2 },
      },
      report_snapshots: [],
    },
    ledger: { dir: `/data/results/${id}`, has_manifest: false, row_count: 0 },
    coverage: {
      declared_cells: 1200,
      completed_cells: 0,
      missing_cells: 1200,
      voided_cells: 0,
      complete_fraction: 0,
      by_arm: {
        A1: { expected: 400, done: 0, missing: 400 },
        A2: { expected: 400, done: 0, missing: 400 },
      },
    },
  };
}

export function mockProjectExperimentRun(
  id: string,
  req: import("./types").ExperimentRunRequest,
): import("./types").ExperimentRunProjection {
  void id;
  void req;
  return {
    projectionText: "1200 runs — 3 arms x 400 tasks x 1 repeats. Rough projection $42.00",
    exitCode: 1,
    stderrNames: [],
    missingCells: 1200,
    voidedCells: 0,
    slice: req.slice ?? null,
    armsScheduled: ["Z0", "A1", "A2"],
  };
}

export function mockStartExperimentRun(
  id: string,
  req: import("./types").ExperimentRunRequest,
): RunJob {
  void req;
  const job: RunJob = {
    id,
    status: "running",
    pid: 4242,
    exitCode: null,
    outDir: `/data/results/${id}`,
    startedAt: new Date().toISOString(),
    finishedAt: null,
    errorKind: null,
    message: null,
  };
  jobs.set(id, job);
  return job;
}

export function mockRunDefaults(): import("./types").RunDefaultsConfig {
  return {
    harness_version: "0.0.1",
    presets: [
      {
        id: "Z0",
        group: "Z",
        label: "No tools",
        description: "No tools — contamination floor",
        requiresSandbox: false,
      },
      {
        id: "A1",
        group: "A",
        label: "Eager MCP",
        description: "Eager MCP — all tools in context",
        requiresSandbox: false,
      },
      {
        id: "A2",
        group: "A",
        label: "Meta-tools MCP",
        description: "Meta-tools MCP — discover + invoke",
        requiresSandbox: false,
      },
      {
        id: "D1",
        group: "D",
        label: "Code filesystem",
        description: "Code filesystem — Python sandbox over module tree",
        requiresSandbox: true,
      },
    ],
    providers: ["openai"],
    models: ["gpt-5.6-luna"],
    providerProfiles: [
      {
        id: "openai",
        label: "OpenAI",
        adapter: "openai",
        models: [{ id: "gpt-5.6-luna", label: "gpt-5.6-luna" }],
      },
    ],
    reasoningEfforts: ["low", "medium", "high"],
    mcpRevisions: ["2026-07-28", "legacy"],
    difficulties: ["easy", "medium", "hard"],
    presetBundles: {
      smoke: ["Z0", "A1", "D1"],
      probe: ["Z0", "A1", "A2", "C1", "D1"],
    },
    defaultRun: {
      id: "local-smoke",
      packId: null,
      targetId: null,
      presets: [],
      model: "gpt-5.6-luna",
      provider: "openai",
      reasoningEffort: "low",
      repeats: 1,
      smoke: true,
      probe: false,
      resume: false,
      dryRun: false,
      allowCodeSandbox: true,
    },
    experimentTemplates: [
      {
        id: "baseline-80",
        label: "Baseline 80-core ladder",
        description: "Authored-skill contrasts on eager, meta-tools, and code-fs.",
        defaults: {
          experimentId: "baseline-experiment-80",
          rationale: "Eighty cores for within-class power.",
          model: "gpt-5.6-luna",
          reasoningEffort: "low",
          repeats: 3,
          surfaceSize: 50,
          mcpRevision: "2026-07-28",
          presets: ["Z0", "A1", "A2", "B1-auth"],
          cores: 80,
          seed: 1,
          fanOut: 8,
          difficulty: "hard",
          maxUsd: 400,
          includeSmokeSlice: true,
        },
      },
    ],
  };
}

const generateTicks = new Map<string, number>();

export function mockStartGenerate(body: StartGenerateRequest): GenerateJob {
  generateTicks.set(body.jobId, 0);
  return {
    jobId: body.jobId,
    status: "accepted",
    workspace: `generate/${body.jobId}`,
  };
}

export function mockGenerateProgress(jobId: string): GenerateProgress {
  const tick = (generateTicks.get(jobId) ?? 0) + 1;
  generateTicks.set(jobId, tick);
  const phases = ["analyze", "materials", "fixtures", "pack", "complete"] as const;
  const idx = Math.min(tick - 1, phases.length - 1);
  const phase = phases[idx];
  const terminal = phase === "complete";
  return {
    job: {
      jobId,
      status: terminal ? "complete" : "running",
      workspace: `generate/${jobId}`,
    },
    terminal,
    status: {
      job_id: jobId,
      phase,
      phases_done: [...phases.slice(0, idx + (terminal ? 1 : 0))].filter(
        (p) => p !== "complete",
      ),
      message: terminal ? "generate complete" : `Running ${phase}`,
      fraction: terminal ? 1 : (idx + 1) / phases.length,
    },
    error: null,
  };
}

export function mockGenerateManifest(jobId: string): GenerateManifestPayload {
  return {
    job_id: jobId,
    pack_path: "pack/pack.yaml",
    pack_id: `${jobId}-pack`,
    graded_tasks: 24,
    fixture_count: 18,
    arms_probe: ["Z0", "A1", "A2", "C1", "D1"],
    validation: "unvalidated",
  };
}

export function mockListGenerateArtifacts(jobId: string): ArtifactRef[] {
  return [
    {
      name: "manifest.json",
      path: `generate/${jobId}/manifest.json`,
      sizeBytes: 420,
    },
    {
      name: "analyze.json",
      path: `generate/${jobId}/analyze.json`,
      sizeBytes: 1200,
    },
    {
      name: "materials/curl-reference.md",
      path: `generate/${jobId}/materials/curl-reference.md`,
      sizeBytes: 2400,
    },
    {
      name: "examples/manifest.yaml",
      path: `generate/${jobId}/examples/manifest.yaml`,
      sizeBytes: 800,
    },
    {
      name: "pack/pack.yaml",
      path: `generate/${jobId}/pack/pack.yaml`,
      sizeBytes: 1600,
    },
  ];
}

export function mockGenerateArtifactText(jobId: string, name: string): string {
  if (name.endsWith(".json")) {
    return JSON.stringify(
      { job_id: jobId, artifact: name, note: "mock generate artifact" },
      null,
      2,
    );
  }
  return `# ${name}\n\nMock generate workspace file for job ${jobId}.\n`;
}

export function mockCreateExperimentFromGenerate(
  jobId: string,
  body: CreateExperimentFromGenerateRequest,
): ExperimentRef {
  void jobId;
  return {
    id: body.experimentId,
    path: `results/${body.experimentId}/experiment.yaml`,
    status: "draft",
  };
}

export function mockDeleteRun(id: string): void {
  jobs.delete(id);
}

export function mockDeletePack(id: string): void {
  void id;
}

export function mockDeleteTarget(id: string): void {
  const i = MOCK_TARGETS.findIndex((t) => t.id === id);
  if (i >= 0) MOCK_TARGETS.splice(i, 1);
}

export function mockDeleteExperiment(id: string): void {
  jobs.delete(id);
}

const mockProviders: ProviderView[] = [
  {
    id: "openai",
    label: "OpenAI",
    adapter: "openai",
    baseUrl: null,
    builtin: true,
    apiKeySet: false,
    apiKeyHint: null,
    processEnvKeySet: false,
    processBaseUrl: null,
    models: [{ id: "gpt-5.6-luna", label: "gpt-5.6-luna", price: null }],
  },
];

export function mockLlmConfig(): LlmConfig {
  return {
    adapters: ["openai"],
    adaptersNote:
      "The engine adapter is openai (or any OpenAI-compatible server via base URL).",
    providers: mockProviders.map((p) => ({ ...p, models: [...p.models] })),
  };
}

export function mockUpsertProvider(
  id: string,
  body: UpsertProviderRequest,
): ProviderView {
  const existing = mockProviders.find((p) => p.id === id);
  const next: ProviderView = {
    id,
    label: body.label || existing?.label || id,
    adapter: body.adapter || "openai",
    baseUrl: body.baseUrl === undefined ? existing?.baseUrl ?? null : body.baseUrl,
    builtin: id === "openai",
    apiKeySet:
      body.apiKey && body.apiKey.length > 0
        ? true
        : body.apiKey === ""
          ? false
          : Boolean(existing?.apiKeySet),
    apiKeyHint:
      body.apiKey && body.apiKey.length > 0
        ? `…${body.apiKey.slice(-4)}`
        : body.apiKey === ""
          ? null
          : existing?.apiKeyHint ?? null,
    processEnvKeySet: existing?.processEnvKeySet ?? false,
    processBaseUrl: existing?.processBaseUrl ?? null,
    models: body.models ?? existing?.models ?? [],
  };
  const i = mockProviders.findIndex((p) => p.id === id);
  if (i >= 0) mockProviders[i] = next;
  else mockProviders.push(next);
  return next;
}

export function mockDeleteProvider(id: string): void {
  const i = mockProviders.findIndex((p) => p.id === id);
  if (i >= 0) mockProviders.splice(i, 1);
}

export function mockUpsertModel(
  providerId: string,
  modelId: string,
  body: UpsertModelRequest,
): ProviderView {
  const p = mockProviders.find((x) => x.id === providerId);
  if (!p) throw new Error(`404 unknown provider: ${providerId}`);
  const i = p.models.findIndex((m) => m.id === modelId);
  const model = {
    id: modelId,
    label: body.label || modelId,
    price: body.price ?? null,
  };
  if (i >= 0) p.models[i] = model;
  else p.models.push(model);
  return p;
}

export function mockDeleteModel(providerId: string, modelId: string): ProviderView {
  const p = mockProviders.find((x) => x.id === providerId);
  if (!p) throw new Error(`404 unknown provider: ${providerId}`);
  p.models = p.models.filter((m) => m.id !== modelId);
  return p;
}
