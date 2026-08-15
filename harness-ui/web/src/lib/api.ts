/**
 * Typed REST client for harness-ui/docs/contracts.md.
 * Base URL defaults to same-origin (""); override with NEXT_PUBLIC_API_BASE.
 * Set NEXT_PUBLIC_API_MOCK=1 to exercise pages without the Java API.
 */

import {
  mockArtifacts,
  mockCompare,
  mockLint,
  mockListCells,
  mockListPacks,
  mockListRuns,
  mockListTargets,
  mockProgress,
  mockProject,
  mockReadPack,
  mockReport,
  mockAnalysis,
  mockStartRun,
  mockTranscript,
  mockUploadTarget,
  mockValidatePack,
  mockWritePack,
  mockListExperiments,
  mockGetExperiment,
  mockProjectExperimentRun,
  mockStartExperimentRun,
  mockRunDefaults,
  mockStartGenerate,
  mockGenerateProgress,
  mockGenerateManifest,
  mockListGenerateArtifacts,
  mockCreateExperimentFromGenerate,
  mockGenerateArtifactText,
  mockDeleteRun,
  mockDeletePack,
  mockDeleteTarget,
  mockDeleteExperiment,
  mockLlmConfig,
  mockUpsertProvider,
  mockDeleteProvider,
  mockUpsertModel,
  mockDeleteModel,
} from "./mock";
import type {
  AdapterLint,
  AdapterAnalysis,
  AdapterReport,
  ArtifactRef,
  CompareResult,
  CostProjection,
  CreateExperimentFromGenerateRequest,
  CreateExperimentRequest,
  ExperimentEnvelope,
  ExperimentRef,
  ExperimentRunProjection,
  ExperimentRunRequest,
  ExperimentSummary,
  GenerateJob,
  GenerateManifestPayload,
  GenerateProgress,
  LlmConfig,
  PackBody,
  PackRef,
  PackValidate,
  PackWriteResult,
  ProgressEnvelope,
  ProviderView,
  ReportSnapshotRef,
  RunJob,
  RunRequest,
  RunDefaultsConfig,
  RunSummary,
  StartGenerateRequest,
  Target,
  TargetContract,
  CellRef,
  TranscriptResponse,
  UpsertModelRequest,
  UpsertProviderRequest,
} from "./types";

const BASE = (process.env.NEXT_PUBLIC_API_BASE ?? "").replace(/\/$/, "");
const MOCK = process.env.NEXT_PUBLIC_API_MOCK === "1";

export function isMockMode(): boolean {
  return MOCK;
}

export async function getRunDefaults(): Promise<RunDefaultsConfig> {
  if (MOCK) return mockRunDefaults();
  return request<RunDefaultsConfig>("/api/v1/config/run-defaults");
}

export function artifactUrl(runId: string, name: string): string {
  return `${BASE}/artifacts/${encodeURIComponent(runId)}/${encodeURIComponent(name)}`;
}

async function request<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const res = await fetch(`${BASE}${path}`, init);
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText}${text ? `: ${text}` : ""}`);
  }
  if (res.status === 204 || res.status === 205) return undefined as T;
  const text = await res.text();
  if (!text) return undefined as T;
  return JSON.parse(text) as T;
}

export async function listTargets(): Promise<Target[]> {
  if (MOCK) return mockListTargets();
  return request<Target[]>("/api/v1/targets");
}

export async function getTarget(id: string): Promise<Target> {
  if (MOCK) {
    const t = mockListTargets().find((x) => x.id === id);
    if (!t) throw new Error(`404 unknown target: ${id}`);
    return t;
  }
  return request<Target>(`/api/v1/targets/${encodeURIComponent(id)}`);
}

export async function readTargetContract(id: string): Promise<TargetContract> {
  if (MOCK) {
    if (id.includes("mcp")) {
      return { text: "http://127.0.0.1:8765/mcp", format: "mcp-url" };
    }
    return {
      text: "openapi: 3.0.3\ninfo:\n  title: Demo\n  version: \"1.0.0\"\npaths: {}\n",
      format: "yaml",
    };
  }
  return request<TargetContract>(
    `/api/v1/targets/${encodeURIComponent(id)}/contract`,
  );
}

export async function writeTargetContract(
  id: string,
  text: string,
): Promise<void> {
  if (MOCK) return;
  await request<void>(`/api/v1/targets/${encodeURIComponent(id)}/contract`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
}

export async function uploadContract(file: File): Promise<Target> {
  if (MOCK) return mockUploadTarget(file.name, "openapi");
  const body = new FormData();
  body.append("file", file);
  return request<Target>("/api/v1/targets", { method: "POST", body });
}

export async function uploadMcpUrl(mcpUrl: string): Promise<Target> {
  if (MOCK) return mockUploadTarget(mcpUrl, "mcp");
  const body = new FormData();
  body.append("mcp_url", mcpUrl);
  return request<Target>("/api/v1/targets", { method: "POST", body });
}

export async function lintTarget(id: string): Promise<AdapterLint> {
  if (MOCK) return mockLint(id);
  return request<AdapterLint>(`/api/v1/targets/${encodeURIComponent(id)}/lint`, {
    method: "POST",
  });
}

export async function draftPack(
  targetId: string,
  outId?: string,
): Promise<{ id: string; path: string; valid: boolean; error: string | null }> {
  if (MOCK) {
    return {
      id: outId ?? `pack-${targetId}`,
      path: `packs/${outId ?? `pack-${targetId}`}.yaml`,
      valid: true,
      error: null,
    };
  }
  return request("/api/v1/packs/draft", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ targetId, outId }),
  });
}

export async function listPacks(): Promise<PackRef[]> {
  if (MOCK) return mockListPacks();
  return request<PackRef[]>("/api/v1/packs");
}

export async function readPack(id: string): Promise<PackBody> {
  if (MOCK) return mockReadPack(id);
  return request<PackBody>(`/api/v1/packs/${encodeURIComponent(id)}`);
}

export async function writePack(
  id: string,
  yaml: string,
): Promise<PackWriteResult> {
  if (MOCK) return mockWritePack(id, yaml);
  return request<PackWriteResult>(`/api/v1/packs/${encodeURIComponent(id)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ yaml }),
  });
}

export async function validatePack(
  id: string,
  baseUrl?: string,
): Promise<PackValidate> {
  if (MOCK) return mockValidatePack(id);
  return request<PackValidate>(
    `/api/v1/packs/${encodeURIComponent(id)}/validate`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ baseUrl }),
    },
  );
}

export async function projectRunCost(
  req: RunRequest,
): Promise<CostProjection> {
  if (MOCK) return mockProject(req);
  return request<CostProjection>("/api/v1/runs/project", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
}

export async function startRun(
  req: RunRequest & { approve: true },
): Promise<RunJob> {
  if (MOCK) return mockStartRun(req);
  return request<RunJob>("/api/v1/runs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
}

export async function getRunProgress(id: string): Promise<ProgressEnvelope> {
  if (MOCK) return mockProgress(id);
  return request<ProgressEnvelope>(
    `/api/v1/runs/${encodeURIComponent(id)}/progress`,
  );
}

export async function listRuns(): Promise<RunSummary[]> {
  if (MOCK) return mockListRuns();
  return request<RunSummary[]>("/api/v1/runs");
}

export async function deleteRun(id: string): Promise<void> {
  if (MOCK) {
    mockDeleteRun(id);
    return;
  }
  await request<void>(`/api/v1/runs/${encodeURIComponent(id)}`, { method: "DELETE" });
}

export async function deletePack(id: string): Promise<void> {
  if (MOCK) {
    mockDeletePack(id);
    return;
  }
  await request<void>(`/api/v1/packs/${encodeURIComponent(id)}`, { method: "DELETE" });
}

export async function deleteTarget(id: string): Promise<void> {
  if (MOCK) {
    mockDeleteTarget(id);
    return;
  }
  await request<void>(`/api/v1/targets/${encodeURIComponent(id)}`, { method: "DELETE" });
}

export async function deleteExperiment(id: string): Promise<void> {
  if (MOCK) {
    mockDeleteExperiment(id);
    return;
  }
  await request<void>(`/api/v1/experiments/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}

export async function getReport(id: string): Promise<AdapterReport> {
  if (MOCK) return mockReport(id);
  return request<AdapterReport>(
    `/api/v1/runs/${encodeURIComponent(id)}/report`,
  );
}

export async function getAnalysis(
  id: string,
  only?: string,
): Promise<AdapterAnalysis> {
  if (MOCK) return mockAnalysis(id, only);
  const q = only ? `?only=${encodeURIComponent(only)}` : "";
  return request<AdapterAnalysis>(
    `/api/v1/runs/${encodeURIComponent(id)}/analysis${q}`,
  );
}

export function artifactPathHref(runId: string, name: string): string {
  const segments = name.split("/").map((s) => encodeURIComponent(s)).join("/");
  return `/runs/${encodeURIComponent(runId)}/artifacts/${segments}/`;
}

export async function listCells(id: string): Promise<CellRef[]> {
  if (MOCK) return mockListCells(id);
  return request<CellRef[]>(`/api/v1/runs/${encodeURIComponent(id)}/cells`);
}

export async function getTranscript(
  id: string,
  arm: string,
  taskId: string,
  repeat: number,
  verbose = false,
): Promise<TranscriptResponse> {
  if (MOCK) return mockTranscript(id, arm, taskId, repeat, verbose);
  const q = verbose ? "?verbose=true" : "";
  return request<TranscriptResponse>(
    `/api/v1/runs/${encodeURIComponent(id)}/transcripts/${encodeURIComponent(arm)}/${encodeURIComponent(taskId)}/${repeat}${q}`,
  );
}

export async function listArtifacts(id: string): Promise<ArtifactRef[]> {
  if (MOCK) return mockArtifacts(id);
  return request<ArtifactRef[]>(
    `/api/v1/runs/${encodeURIComponent(id)}/artifacts`,
  );
}

export async function compareRuns(runIds: string[]): Promise<CompareResult> {
  if (MOCK) return mockCompare(runIds);
  return request<CompareResult>("/api/v1/compare", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ runIds }),
  });
}

/** Cache last-viewed report JSON for the offline service worker. */
export function cacheReportOffline(runId: string, report: AdapterReport): void {
  try {
    localStorage.setItem(
      "harness-ui:last-report",
      JSON.stringify({ runId, report, savedAt: Date.now() }),
    );
  } catch {
    /* quota / private mode */
  }
}

export function readCachedReport(): {
  runId: string;
  report: AdapterReport;
  savedAt: number;
} | null {
  try {
    const raw = localStorage.getItem("harness-ui:last-report");
    if (!raw) return null;
    return JSON.parse(raw) as {
      runId: string;
      report: AdapterReport;
      savedAt: number;
    };
  } catch {
    return null;
  }
}

export async function listExperiments(all = false): Promise<ExperimentSummary[]> {
  if (MOCK) return mockListExperiments();
  const q = all ? "?all=true" : "";
  return request<ExperimentSummary[]>(`/api/v1/experiments${q}`);
}

export async function createExperiment(
  body: CreateExperimentRequest,
): Promise<ExperimentRef> {
  if (MOCK) {
    return {
      id: body.id,
      path: `results/${body.id}/experiment.yaml`,
      status: "draft",
    };
  }
  return request<ExperimentRef>("/api/v1/experiments", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export async function getExperiment(
  id: string,
  slice?: string,
): Promise<ExperimentEnvelope> {
  if (MOCK) return mockGetExperiment(id);
  const q = slice ? `?slice=${encodeURIComponent(slice)}` : "";
  return request<ExperimentEnvelope>(`/api/v1/experiments/${encodeURIComponent(id)}${q}`);
}

export async function addExperimentArms(
  id: string,
  presets: string[],
): Promise<ExperimentRef> {
  if (MOCK) {
    return { id, path: `results/${id}/experiment.yaml`, status: "active" };
  }
  return request<ExperimentRef>(`/api/v1/experiments/${encodeURIComponent(id)}/arms`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ presets }),
  });
}

export async function projectExperimentRun(
  id: string,
  req: ExperimentRunRequest,
): Promise<ExperimentRunProjection> {
  if (MOCK) return mockProjectExperimentRun(id, req);
  return request<ExperimentRunProjection>(
    `/api/v1/experiments/${encodeURIComponent(id)}/run/project`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req),
    },
  );
}

export async function startExperimentRun(
  id: string,
  req: ExperimentRunRequest & { approve: true },
): Promise<RunJob> {
  if (MOCK) return mockStartExperimentRun(id, req);
  return request<RunJob>(`/api/v1/experiments/${encodeURIComponent(id)}/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
}

export async function listExperimentReports(
  id: string,
): Promise<ReportSnapshotRef[]> {
  if (MOCK) return [];
  return request<ReportSnapshotRef[]>(
    `/api/v1/experiments/${encodeURIComponent(id)}/reports`,
  );
}

export async function snapshotExperimentReport(
  id: string,
): Promise<ReportSnapshotRef> {
  if (MOCK) {
    return {
      at: new Date().toISOString(),
      status: "active",
      path: `reports/mock-${Date.now()}.json`,
      ledgerRows: 0,
    };
  }
  return request<ReportSnapshotRef>(
    `/api/v1/experiments/${encodeURIComponent(id)}/reports/snapshot`,
    { method: "POST" },
  );
}

export async function startGenerate(
  body: StartGenerateRequest,
): Promise<GenerateJob> {
  if (MOCK) return mockStartGenerate(body);
  return request<GenerateJob>("/api/v1/generate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export async function getGenerateProgress(
  jobId: string,
): Promise<GenerateProgress> {
  if (MOCK) return mockGenerateProgress(jobId);
  return request<GenerateProgress>(
    `/api/v1/generate/${encodeURIComponent(jobId)}/progress`,
  );
}

export async function getGenerateManifest(
  jobId: string,
): Promise<GenerateManifestPayload> {
  if (MOCK) return mockGenerateManifest(jobId);
  return request<GenerateManifestPayload>(
    `/api/v1/generate/${encodeURIComponent(jobId)}/manifest`,
  );
}

export async function listGenerateArtifacts(
  jobId: string,
): Promise<ArtifactRef[]> {
  if (MOCK) return mockListGenerateArtifacts(jobId);
  return request<ArtifactRef[]>(
    `/api/v1/generate/${encodeURIComponent(jobId)}/artifacts`,
  );
}

export function generateArtifactUrl(jobId: string, name: string): string {
  const segments = name.split("/").map((s) => encodeURIComponent(s)).join("/");
  return `${BASE}/api/v1/generate/${encodeURIComponent(jobId)}/artifacts/${segments}`;
}

export async function getGenerateArtifactText(
  jobId: string,
  name: string,
): Promise<string> {
  if (MOCK) return mockGenerateArtifactText(jobId, name);
  const res = await fetch(generateArtifactUrl(jobId, name));
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText}${text ? `: ${text}` : ""}`);
  }
  return res.text();
}

export async function createExperimentFromGenerate(
  jobId: string,
  body: CreateExperimentFromGenerateRequest,
): Promise<ExperimentRef> {
  if (MOCK) return mockCreateExperimentFromGenerate(jobId, body);
  return request<ExperimentRef>(
    `/api/v1/generate/${encodeURIComponent(jobId)}/experiment`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
  );
}

export async function getLlmConfig(): Promise<LlmConfig> {
  if (MOCK) return mockLlmConfig();
  return request<LlmConfig>("/api/v1/config/llm");
}

export async function upsertProvider(
  id: string,
  body: UpsertProviderRequest,
): Promise<ProviderView> {
  if (MOCK) return mockUpsertProvider(id, body);
  return request<ProviderView>(
    `/api/v1/config/providers/${encodeURIComponent(id)}`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
  );
}

export async function deleteProvider(id: string): Promise<void> {
  if (MOCK) {
    mockDeleteProvider(id);
    return;
  }
  await request<void>(`/api/v1/config/providers/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}

export async function upsertModel(
  providerId: string,
  modelId: string,
  body: UpsertModelRequest,
): Promise<ProviderView> {
  if (MOCK) return mockUpsertModel(providerId, modelId, body);
  return request<ProviderView>(
    `/api/v1/config/providers/${encodeURIComponent(providerId)}/models/${encodeURIComponent(modelId)}`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
  );
}

export async function deleteModel(
  providerId: string,
  modelId: string,
): Promise<ProviderView> {
  if (MOCK) return mockDeleteModel(providerId, modelId);
  return request<ProviderView>(
    `/api/v1/config/providers/${encodeURIComponent(providerId)}/models/${encodeURIComponent(modelId)}`,
    { method: "DELETE" },
  );
}
