import type {
  AdapterLint,
  AdapterReport,
  ArtifactRef,
  CompareResult,
  CostProjection,
  PackBody,
  PackValidate,
  PackWriteResult,
  ProgressEnvelope,
  RunJob,
  RunRequest,
  RunSummary,
  Target,
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
