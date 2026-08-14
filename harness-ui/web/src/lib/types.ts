/** Shared DTOs — shapes frozen in harness-ui/docs/contracts.md */

export type Target = {
  id: string;
  kind: "openapi" | "mcp";
  label: string;
  createdAt: string;
};

export type TargetContract = {
  text: string;
  format: "yaml" | "json" | "mcp-url";
};

export type PackRef = {
  id: string;
  path: string;
  valid: boolean;
  error: string | null;
};

export type PackBody = {
  id: string;
  yaml: string;
};

export type PackWriteResult = {
  id: string;
  valid: boolean;
  error?: string | null;
};

export type RunRequest = {
  id: string;
  packId: string | null;
  targetId: string | null;
  presets: string[];
  model: string;
  provider: string;
  reasoningEffort: string;
  repeats: number;
  smoke: boolean;
  probe: boolean;
  resume: boolean;
  dryRun: boolean;
  allowCodeSandbox: boolean;
};

export type CostProjection = {
  projectionText: string;
  exitCode: number;
  stderrNames: string[];
};

export type RunStatus =
  | "queued"
  | "running"
  | "succeeded"
  | "failed"
  | "cancelled"
  | "declined";

export type RunJob = {
  id: string;
  status: RunStatus;
  pid: number | null;
  exitCode: number | null;
  outDir: string;
  startedAt: string;
  finishedAt: string | null;
  errorKind: string | null;
  message: string | null;
};

export type RunSummary = {
  id: string;
  status: RunStatus | string;
  outDir?: string | null;
  model?: string | null;
  startedAt?: string | null;
  finishedAt?: string | null;
  message?: string | null;
  ledgerRows?: number | null;
};

export type CompareResult = {
  refused: boolean;
  refusalText: string | null;
  brokenBoundary: string | null;
  artifactDir: string | null;
  stdout: string;
};

export type ArtifactRef = {
  name: string;
  path: string;
  contentType?: string | null;
  sizeBytes?: number | null;
};

export type CellRef = {
  arm: string;
  taskId: string;
  repeat: number;
  outcome: string | null;
  turns: number;
  calls: number;
};

export type TranscriptResponse = {
  text: string;
};

export type AdapterProgress = {
  harness_version: string;
  done: number;
  expected: number | null;
  fraction: number | null;
  eta_seconds: number | null;
  elapsed_seconds: number;
  started_at: string | null;
  by_arm: Record<string, number>;
  outcomes: Record<string, number>;
};

export type ProgressEnvelope = {
  job: RunJob;
  progress: AdapterProgress | null;
  terminal: boolean;
};

export type LintFinding = {
  rule_id: string;
  severity: "high" | "medium" | "low";
  confidence: "measured" | "heuristic";
  message: string;
  location?: string | null;
};

export type AdapterLint = {
  harness_version: string;
  spec_path?: string;
  findings: LintFinding[];
  rules_run: number;
  rules_measured: number;
  measured_fraction: number;
  footer: string;
};

export type AdapterArm = {
  arm: string;
  name?: string;
  label?: string;
  description?: string;
  is_control: boolean;
  n: number;
  graded?: number;
  success_rate?: number | null;
  harm_rate?: number;
  composite_score?: number | null;
  cost_per_success_usd?: number | null;
  lift?: number | null;
  below_mde?: boolean;
};

export type AdapterReport = {
  harness_version: string;
  run: {
    id: string;
    model: string;
    provider?: string | null;
    report_class: string;
    n_rows: number;
    pooling_refused: boolean;
    presets?: string[];
  };
  verdict: {
    winner: string | null;
    leader?: string | null;
    runner_up?: string | null;
    reason: string;
    scores: Record<string, number>;
    caveats: string[];
  };
  arms: Record<string, AdapterArm>;
  validation: "validated-controlled" | "unvalidated" | "heuristic";
};

export type AnalysisSection = {
  title: string;
  note?: string;
  headers: string[];
  rows: Record<string, unknown>[];
};

export type AdapterAnalysis = {
  harness_version: string;
  run: {
    id?: string | null;
    model?: string | null;
    report_class?: string | null;
  };
  generated_from: string;
  sections: Record<string, AnalysisSection>;
};

export type PackValidate = {
  harness_version: string;
  path?: string;
  valid: boolean;
  error: string | null;
  pack_id?: string | null;
  task_count?: number | null;
};

export type ExperimentSummary = {
  /** Results directory name — use this in /experiments/{id}/ URLs. */
  id: string;
  status: string;
  hasLedger: boolean;
  coverageFraction: number | null;
  model?: string | null;
  updatedAt?: string | null;
  /** Sidecar plan id when it differs from the directory name. */
  planId?: string | null;
};

export type ExperimentRef = {
  id: string;
  path: string;
  status: string;
  error?: string | null;
};

export type ExperimentCoverage = {
  declared_cells: number;
  completed_cells: number;
  missing_cells: number;
  voided_cells: number;
  complete_fraction: number | null;
  by_arm: Record<string, { expected: number; done: number; missing: number }>;
};

export type ExperimentEnvelope = {
  harness_version: string;
  schema_version: number;
  experiment: {
    id: string;
    status: string;
    run_plan?: { include?: { presets?: string[] }; tasks?: { generate?: Record<string, unknown> } };
    slices?: Record<string, { description?: string; arms?: string[]; cores?: number }>;
    report_snapshots?: ReportSnapshotRef[];
  };
  ledger: {
    dir: string;
    has_manifest: boolean;
    row_count: number;
  };
  coverage: ExperimentCoverage;
};

export type ExperimentRunRequest = {
  slice?: string | null;
  approve?: boolean;
  allowCodeSandbox?: boolean;
  concurrency?: number;
};

export type ExperimentRunProjection = CostProjection & {
  missingCells: number;
  voidedCells: number;
  slice?: string | null;
  armsScheduled?: string[];
};

export type ReportSnapshotRef = {
  at: string;
  status?: string | null;
  path?: string | null;
  ledgerRows?: number;
};

export type CreateExperimentRequest = {
  id: string;
  yaml?: string;
  planPath?: string;
};

export type PresetOption = {
  id: string;
  group: string;
  label: string;
  /** Full sentence from axes.describe — for tooltips / matrix. */
  description?: string;
  requiresSandbox: boolean;
};

export type GenerateStaging = {
  baseUrlEnv: string;
  authEnv?: string | null;
  seed?: number | null;
  /** Optional value stored under /data/secrets/ and injected into the CLI env. */
  baseUrl?: string | null;
  /** Optional token stored under /data/secrets/ (never in pack YAML). */
  authToken?: string | null;
};

export type GeneratePhases = {
  analyze?: boolean;
  materials?: boolean;
  fixtures?: boolean;
  pack?: boolean;
  enrich?: boolean;
};

export type StartGenerateRequest = {
  jobId: string;
  targetId: string;
  staging: GenerateStaging;
  phases?: GeneratePhases;
  approveEnrich?: boolean;
  /** Keep A/B MCP arms — requires MCP gateway for field HTTP APIs. */
  mcpGateway?: boolean;
  /** Start local OpenAPI HTTP mock + MCP gateway; no staging URL required. */
  useLocalMock?: boolean;
  /**
   * Customer MCP gateway URL → generate.config `mcp_url` / pack `api.mcp.url`.
   * Ignored when useLocalMock is true.
   */
  mcpUrl?: string | null;
};

export type GenerateJob = {
  jobId: string;
  status: "accepted" | "running" | "complete" | "failed";
  workspace: string;
};

export type GenerateStatusPayload = {
  job_id: string;
  phase: string;
  phases_done: string[];
  message: string;
  fraction?: number | null;
  started_at?: string;
  updated_at?: string;
  cost_usd_so_far?: number | null;
};

export type GenerateProgress = {
  job: GenerateJob;
  terminal: boolean;
  status: GenerateStatusPayload | null;
  error: { exit_code: number; kind: string; message: string } | null;
};

export type GenerateManifestPayload = {
  job_id: string;
  pack_path?: string | null;
  pack_id?: string | null;
  graded_tasks?: number | null;
  fixture_count?: number | null;
  arms_probe?: string[];
  validation?: string;
};

export type GenerateManifest = {
  harness_version: string;
  manifest: GenerateManifestPayload;
};

export type CreateExperimentFromGenerateRequest = {
  experimentId: string;
  planOverrides?: string | null;
};

export type ExperimentPlanDefaults = {
  experimentId: string;
  rationale: string;
  model: string;
  provider?: string;
  reasoningEffort: string;
  repeats: number;
  surfaceSize: number;
  mcpRevision: string;
  presets: string[];
  cores: number;
  seed: number;
  fanOut: number;
  difficulty: string;
  maxUsd: number;
  includeSmokeSlice: boolean;
};

export type ExperimentTemplate = {
  id: string;
  label: string;
  description: string;
  defaults: ExperimentPlanDefaults;
};

export type RunDefaultsConfig = {
  harness_version: string;
  presets: PresetOption[];
  providers: string[];
  models: string[];
  reasoningEfforts: string[];
  mcpRevisions: string[];
  difficulties: string[];
  presetBundles: Record<string, string[]>;
  defaultRun: RunRequest;
  experimentTemplates: ExperimentTemplate[];
  providerProfiles?: ProviderProfile[];
};

export type ProviderProfile = {
  id: string;
  label: string;
  adapter: string;
  models: Array<{ id: string; label?: string }>;
};

export type RegisteredModel = {
  id: string;
  label?: string | null;
  price?: string | null;
};

export type ProviderView = {
  id: string;
  label: string;
  adapter: string;
  baseUrl?: string | null;
  builtin: boolean;
  apiKeySet: boolean;
  apiKeyHint?: string | null;
  processEnvKeySet: boolean;
  processBaseUrl?: string | null;
  models: RegisteredModel[];
};

export type LlmConfig = {
  adapters: string[];
  adaptersNote: string;
  providers: ProviderView[];
};

export type UpsertProviderRequest = {
  label?: string | null;
  adapter?: string | null;
  baseUrl?: string | null;
  apiKey?: string | null;
  models?: RegisteredModel[] | null;
};

export type UpsertModelRequest = {
  label?: string | null;
  price?: string | null;
};

/** Models the run/experiment pickers should offer for a provider profile. */
export function modelsForProvider(
  config: RunDefaultsConfig,
  providerId: string,
): Array<{ id: string; label?: string }> {
  const profile = config.providerProfiles?.find((p) => p.id === providerId);
  if (profile && profile.models.length > 0) {
    return profile.models.map((m) => ({
      id: m.id,
      label: m.label && m.label !== m.id ? m.label : m.id,
    }));
  }
  if (providerId === "openai" || !providerId) {
    return config.models.map((id) => ({ id, label: id }));
  }
  return [];
}
