/**
 * Typed REST client for harness-ui/docs/contracts.md.
 * Base URL defaults to same-origin (""); override with NEXT_PUBLIC_API_BASE.
 * Set NEXT_PUBLIC_API_MOCK=1 to exercise pages without the Java API.
 */

import {
  mockArtifacts,
  mockCompare,
  mockLint,
  mockListRuns,
  mockListTargets,
  mockProgress,
  mockProject,
  mockReadPack,
  mockReport,
  mockStartRun,
  mockUploadTarget,
  mockValidatePack,
  mockWritePack,
} from "./mock";
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

const BASE = (process.env.NEXT_PUBLIC_API_BASE ?? "").replace(/\/$/, "");
const MOCK = process.env.NEXT_PUBLIC_API_MOCK === "1";

export function isMockMode(): boolean {
  return MOCK;
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
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export async function listTargets(): Promise<Target[]> {
  if (MOCK) return mockListTargets();
  return request<Target[]>("/api/v1/targets");
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

export async function getReport(id: string): Promise<AdapterReport> {
  if (MOCK) return mockReport(id);
  return request<AdapterReport>(
    `/api/v1/runs/${encodeURIComponent(id)}/report`,
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
