/** Shared DTOs — shapes frozen in harness-ui/docs/contracts.md */

export type Target = {
  id: string;
  kind: "openapi" | "mcp";
  label: string;
  createdAt: string;
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
  status: RunStatus;
  model?: string | null;
  startedAt?: string | null;
  finishedAt?: string | null;
  message?: string | null;
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

export type PackValidate = {
  harness_version: string;
  path?: string;
  valid: boolean;
  error: string | null;
  pack_id?: string | null;
  task_count?: number | null;
};
