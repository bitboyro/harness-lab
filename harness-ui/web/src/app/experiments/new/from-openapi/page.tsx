"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, type FormEvent } from "react";

import { ArmChip } from "@/components/ArmChip";
import {
  createExperimentFromGenerate,
  getGenerateArtifactText,
  getGenerateManifest,
  getGenerateProgress,
  lintTarget,
  listGenerateArtifacts,
  startGenerate,
  uploadContract,
} from "@/lib/api";
import type {
  AdapterLint,
  ArtifactRef,
  GenerateManifestPayload,
  GenerateProgress,
  Target,
} from "@/lib/types";

const STEPS = [
  "Upload",
  "Lint",
  "Staging",
  "Generate",
  "Review",
  "Experiment",
] as const;

type Step = (typeof STEPS)[number];

const MIN_GRADED = 20;

function slugify(raw: string): string {
  return raw
    .toLowerCase()
    .replace(/\.[^.]+$/, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "")
    .slice(0, 40) || "openapi-job";
}

export default function FromOpenApiWizardPage() {
  const router = useRouter();
  const [step, setStep] = useState<Step>("Upload");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [target, setTarget] = useState<Target | null>(null);
  const [lint, setLint] = useState<AdapterLint | null>(null);

  const [jobId, setJobId] = useState("");
  const [experimentId, setExperimentId] = useState("");
  const [baseUrlEnv, setBaseUrlEnv] = useState("TARGET_BASE_URL");
  const [authEnv, setAuthEnv] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [authToken, setAuthToken] = useState("");
  const [seed, setSeed] = useState(42);
  const [runFixtures, setRunFixtures] = useState(true);
  const [runPack, setRunPack] = useState(true);
  const [runEnrich, setRunEnrich] = useState(false);
  const [approveEnrich, setApproveEnrich] = useState(false);
  const [mcpGateway, setMcpGateway] = useState(false);
  const [useLocalMock, setUseLocalMock] = useState(true);
  const [mcpUrl, setMcpUrl] = useState("");
  const [ackGoldFree, setAckGoldFree] = useState(false);

  const [progress, setProgress] = useState<GenerateProgress | null>(null);
  const [manifest, setManifest] = useState<GenerateManifestPayload | null>(null);
  const [artifacts, setArtifacts] = useState<ArtifactRef[]>([]);
  const [previewName, setPreviewName] = useState<string | null>(null);
  const [previewText, setPreviewText] = useState<string | null>(null);

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  function stopPolling() {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }

  async function onUpload(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const fileInput = form.elements.namedItem("spec") as HTMLInputElement;
    const file = fileInput.files?.[0];
    if (!file) {
      setError("Choose an OpenAPI JSON or YAML file.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const t = await uploadContract(file);
      if (t.kind !== "openapi") {
        setError("Generate needs an OpenAPI target.");
        return;
      }
      setTarget(t);
      const base = slugify(file.name);
      setJobId(`${base}-gen`);
      setExperimentId(`${base}-probe`);
      setLint(null);
      setStep("Lint");
      setBusy(true);
      const card = await lintTarget(t.id);
      setLint(card);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function onStartGenerate(e: FormEvent) {
    e.preventDefault();
    if (!target) return;
    if (!jobId.trim() || !experimentId.trim()) {
      setError("job id and experiment id are required");
      return;
    }
    if (runEnrich && !approveEnrich) {
      setError("Approve enrich spend (or turn enrich off) before starting.");
      return;
    }
    setBusy(true);
    setError(null);
    setProgress(null);
    setManifest(null);
    setArtifacts([]);
    try {
      const job = await startGenerate({
        jobId: jobId.trim(),
        targetId: target.id,
        staging: {
          baseUrlEnv: baseUrlEnv.trim() || "TARGET_BASE_URL",
          authEnv: authEnv.trim() || null,
          seed,
          baseUrl: baseUrl.trim() || null,
          authToken: authToken.trim() || null,
        },
        phases: {
          analyze: true,
          materials: true,
          fixtures: runFixtures,
          pack: runPack,
          enrich: runEnrich,
        },
        approveEnrich: runEnrich ? approveEnrich : undefined,
        mcpGateway: useLocalMock ? true : mcpGateway || Boolean(mcpUrl.trim()),
        useLocalMock,
        mcpUrl: useLocalMock ? null : mcpUrl.trim() || null,
      });
      setProgress({
        job,
        terminal: false,
        status: null,
        error: null,
      });
      setStep("Generate");
      stopPolling();
      pollRef.current = setInterval(() => {
        void getGenerateProgress(job.jobId)
          .then(async (env) => {
            setProgress(env);
            if (!env.terminal) return;
            stopPolling();
            if (env.job.status === "failed" || env.error) {
              setError(
                env.error?.message ??
                  `generate failed (${env.job.status})`,
              );
              return;
            }
            try {
              const [man, arts] = await Promise.all([
                getGenerateManifest(job.jobId),
                listGenerateArtifacts(job.jobId),
              ]);
              setManifest(man);
              setArtifacts(arts);
              setStep("Review");
            } catch (err) {
              setError(err instanceof Error ? err.message : String(err));
            }
          })
          .catch((err: Error) => {
            setError(err.message);
            stopPolling();
          });
      }, 800);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function onPreview(name: string) {
    if (!progress) return;
    setPreviewName(name);
    setPreviewText(null);
    setError(null);
    try {
      setPreviewText(await getGenerateArtifactText(progress.job.jobId, name));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function onCreateExperiment() {
    if (!progress || !manifest) return;
    const graded = manifest.graded_tasks ?? 0;
    if (graded < MIN_GRADED && !ackGoldFree) {
      setError(
        `Only ${graded} graded tasks (min ${MIN_GRADED}). Acknowledge gold-free probe to continue.`,
      );
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const ref = await createExperimentFromGenerate(progress.job.jobId, {
        experimentId: experimentId.trim(),
      });
      setStep("Experiment");
      router.push(`/experiments/${encodeURIComponent(ref.id)}/`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  const stepIndex = STEPS.indexOf(step);
  const graded = manifest?.graded_tasks ?? 0;
  const belowMin = manifest != null && graded < MIN_GRADED;

  const previewables = artifacts.filter((a) =>
    /\.(json|ya?ml|md|xml|txt)$/i.test(a.name),
  );

  return (
    <div className="max-w-3xl space-y-6">
      <div>
        <p className="section-label">
          <Link href="/experiments/">Experiments</Link>
          {" / "}
          <Link href="/experiments/new/">New</Link>
        </p>
        <h1 className="page-title">From OpenAPI</h1>
        <p className="page-lede">
          Upload a spec, lint it, generate materials + pack from staging, then
          create a field experiment. Probe spend still happens on the detail
          page after you approve.
        </p>
      </div>

      <ol className="wizard-steps" aria-label="Wizard steps">
        {STEPS.map((label, i) => (
          <li
            key={label}
            className={
              i < stepIndex
                ? "done"
                : i === stepIndex
                  ? "current"
                  : undefined
            }
          >
            <span className="wizard-step-index">{i + 1}</span>
            {label}
          </li>
        ))}
      </ol>

      {error && <p className="alert-error">{error}</p>}

      {step === "Upload" && (
        <form className="panel space-y-4" onSubmit={onUpload}>
          <p className="text-sm" style={{ color: "var(--muted)" }}>
            OpenAPI JSON or YAML only. MCP URLs belong on Targets → draft pack.
          </p>
          <label className="block text-sm">
            Spec file
            <input
              name="spec"
              type="file"
              accept=".json,.yaml,.yml,application/json,text/yaml"
              className="mt-1 block w-full text-sm"
              required
            />
          </label>
          <div className="cta-row">
            <button type="submit" className="btn btn-primary" disabled={busy}>
              {busy ? "Uploading…" : "Upload & lint"}
            </button>
            <Link href="/experiments/new/" className="btn btn-ghost">
              Plan template instead
            </Link>
          </div>
        </form>
      )}

      {step === "Lint" && target && (
        <div className="space-y-4">
          <div className="panel space-y-2">
            <p className="text-sm">
              Target{" "}
              <span className="font-mono">{target.id}</span>
              <span className="ml-2" style={{ color: "var(--muted)" }}>
                {target.label}
              </span>
            </p>
            {!lint && (
              <p className="text-sm" style={{ color: "var(--muted)" }}>
                Running lint…
              </p>
            )}
            {lint && (
              <>
                <div className="overflow-x-auto">
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Rule</th>
                        <th>Severity</th>
                        <th>Message</th>
                      </tr>
                    </thead>
                    <tbody>
                      {lint.findings.slice(0, 12).map((f, i) => (
                        <tr key={`${f.rule_id}-${i}`}>
                          <td className="font-mono">{f.rule_id}</td>
                          <td>{f.severity}</td>
                          <td>{f.message}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {lint.findings.length > 12 && (
                  <p className="text-xs" style={{ color: "var(--muted)" }}>
                    Showing 12 of {lint.findings.length}.{" "}
                    <Link href={`/targets/${encodeURIComponent(target.id)}/lint/`}>
                      Full lint
                    </Link>
                  </p>
                )}
                <p className="font-mono text-xs" style={{ color: "var(--muted)" }}>
                  {lint.footer}
                </p>
              </>
            )}
          </div>
          <div className="cta-row">
            <button
              type="button"
              className="btn btn-primary"
              disabled={!lint || busy}
              onClick={() => setStep("Staging")}
            >
              Configure staging
            </button>
            <button
              type="button"
              className="btn btn-ghost"
              onClick={() => {
                setTarget(null);
                setLint(null);
                setStep("Upload");
              }}
            >
              Back
            </button>
          </div>
        </div>
      )}

      {step === "Staging" && (
        <form className="panel space-y-4" onSubmit={onStartGenerate}>
          <p className="text-sm" style={{ color: "var(--muted)" }}>
            Prefer <strong>Use local mock</strong> when you have no staging
            URL — we start an OpenAPI HTTP stub + MCP gateway on localhost.
            Otherwise provide staging values under{" "}
            <code>/data/secrets/</code> (never written into pack YAML).
          </p>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={useLocalMock}
              onChange={(e) => {
                setUseLocalMock(e.target.checked);
                if (e.target.checked) {
                  setMcpGateway(true);
                  setBaseUrl("");
                  setMcpUrl("");
                }
              }}
            />
            Use local mock (no staging URL)
          </label>
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="block text-sm">
              Generate job id
              <input
                className="field-input"
                value={jobId}
                onChange={(e) => setJobId(e.target.value)}
                required
              />
            </label>
            <label className="block text-sm">
              Experiment id
              <input
                className="field-input"
                value={experimentId}
                onChange={(e) => setExperimentId(e.target.value)}
                required
              />
            </label>
            {!useLocalMock && (
              <>
                <label className="block text-sm">
                  Base URL env
                  <input
                    className="field-input"
                    value={baseUrlEnv}
                    onChange={(e) => setBaseUrlEnv(e.target.value)}
                    required
                  />
                </label>
                <label className="block text-sm">
                  Staging base URL (optional value)
                  <input
                    className="field-input"
                    value={baseUrl}
                    onChange={(e) => setBaseUrl(e.target.value)}
                    placeholder="http://127.0.0.1:8765"
                  />
                </label>
                <label className="block text-sm sm:col-span-2">
                  MCP URL (optional)
                  <input
                    type="url"
                    className="field-input"
                    value={mcpUrl}
                    onChange={(e) => {
                      const v = e.target.value;
                      setMcpUrl(v);
                      if (v.trim()) setMcpGateway(true);
                    }}
                    placeholder="https://mcp.customer.com/mcp"
                  />
                  <span
                    className="mt-1 block text-xs"
                    style={{ color: "var(--muted)" }}
                  >
                    Packs into{" "}
                    <code>api.mcp.url</code> for A1/A2. Leave empty for Z0/C1/D1
                    only (unless you already have a gateway and check the box
                    below).
                  </span>
                </label>
                <label className="block text-sm">
                  Auth env (optional)
                  <input
                    className="field-input"
                    value={authEnv}
                    onChange={(e) => setAuthEnv(e.target.value)}
                    placeholder="TARGET_TOKEN"
                  />
                </label>
                <label className="block text-sm">
                  Auth token (optional value)
                  <input
                    type="password"
                    className="field-input"
                    value={authToken}
                    onChange={(e) => setAuthToken(e.target.value)}
                    autoComplete="off"
                  />
                </label>
              </>
            )}
            <label className="block text-sm">
              Fixture seed
              <input
                type="number"
                className="field-input"
                value={seed}
                onChange={(e) => setSeed(Number(e.target.value) || 0)}
              />
            </label>
          </div>
          <div className="flex flex-wrap gap-4 text-sm">
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={runFixtures}
                onChange={(e) => setRunFixtures(e.target.checked)}
              />
              Capture fixtures
            </label>
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={runPack}
                onChange={(e) => setRunPack(e.target.checked)}
              />
              Build pack
            </label>
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={runEnrich}
                onChange={(e) => {
                  setRunEnrich(e.target.checked);
                  if (!e.target.checked) setApproveEnrich(false);
                }}
              />
              LLM enrich (costs $)
            </label>
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={
                  useLocalMock ? true : mcpGateway || Boolean(mcpUrl.trim())
                }
                disabled={useLocalMock || Boolean(mcpUrl.trim())}
                onChange={(e) => setMcpGateway(e.target.checked)}
              />
              MCP gateway available
            </label>
          </div>
          {runEnrich && (
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={approveEnrich}
                onChange={(e) => setApproveEnrich(e.target.checked)}
              />
              I approve enrich spend (cap $2, model gpt-5.6-luna)
            </label>
          )}
          {useLocalMock ? (
            <p className="text-xs" style={{ color: "var(--muted)" }}>
              Local mock enables A1/A2 arms via an in-process MCP gateway over
              the stub HTTP API. See{" "}
              <code>harness-ui/docs/mcp-gateway.md</code>.
            </p>
          ) : mcpUrl.trim() ? (
            <p className="text-xs" style={{ color: "var(--muted)" }}>
              MCP URL enables A1/A2 against your gateway; C1/D1 still use{" "}
              <code>$TARGET_BASE_URL</code> (staging). See{" "}
              <code>harness-ui/docs/mcp-gateway.md</code>.
            </p>
          ) : (
            !mcpGateway && (
              <p className="text-xs" style={{ color: "var(--muted)" }}>
                Without an MCP gateway, probe arms stay on Z0 / C1 / D1
                (docs+curl / code-fs). See{" "}
                <code>harness-ui/docs/mcp-gateway.md</code>.
              </p>
            )
          )}
          <div className="cta-row">
            <button type="submit" className="btn btn-primary" disabled={busy}>
              {busy ? "Starting…" : "Start generate"}
            </button>
            <button
              type="button"
              className="btn btn-ghost"
              onClick={() => setStep("Lint")}
            >
              Back
            </button>
          </div>
        </form>
      )}

      {step === "Generate" && progress && (
        <div className="panel space-y-3">
          <p className="text-sm font-mono">
            job {progress.job.jobId} · {progress.job.status}
          </p>
          {progress.status && (
            <>
              <p className="text-sm">
                Phase <span className="font-mono">{progress.status.phase}</span>
                {progress.status.fraction != null && (
                  <span style={{ color: "var(--muted)" }}>
                    {" "}
                    · {Math.round(progress.status.fraction * 100)}%
                  </span>
                )}
              </p>
              <div
                className="wizard-progress"
                role="progressbar"
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={Math.round((progress.status.fraction ?? 0) * 100)}
              >
                <div
                  style={{
                    width: `${Math.round((progress.status.fraction ?? 0) * 100)}%`,
                  }}
                />
              </div>
              <p className="text-sm" style={{ color: "var(--muted)" }}>
                {progress.status.message}
              </p>
              {progress.status.phases_done.length > 0 && (
                <p className="font-mono text-xs" style={{ color: "var(--muted)" }}>
                  done: {progress.status.phases_done.join(", ")}
                </p>
              )}
            </>
          )}
          {!progress.status && (
            <p className="text-sm" style={{ color: "var(--muted)" }}>
              Waiting for status…
            </p>
          )}
        </div>
      )}

      {step === "Review" && manifest && (
        <div className="space-y-4">
          <div className="panel space-y-3">
            <h2 className="text-lg font-medium">Manifest</h2>
            <dl className="grid gap-2 text-sm sm:grid-cols-2">
              <div>
                <dt style={{ color: "var(--muted)" }}>Pack</dt>
                <dd className="font-mono">{manifest.pack_id ?? "—"}</dd>
              </div>
              <div>
                <dt style={{ color: "var(--muted)" }}>Graded tasks</dt>
                <dd className="font-mono">{manifest.graded_tasks ?? 0}</dd>
              </div>
              <div>
                <dt style={{ color: "var(--muted)" }}>Fixtures</dt>
                <dd className="font-mono">{manifest.fixture_count ?? 0}</dd>
              </div>
              <div>
                <dt style={{ color: "var(--muted)" }}>Validation</dt>
                <dd className="font-mono">{manifest.validation ?? "—"}</dd>
              </div>
              <div className="sm:col-span-2">
                <dt style={{ color: "var(--muted)" }}>Probe arms</dt>
                <dd className="flex flex-wrap gap-2 pt-1">
                  {(manifest.arms_probe ?? []).length === 0
                    ? "—"
                    : (manifest.arms_probe ?? []).map((a) => (
                        <ArmChip key={a} arm={a} />
                      ))}
                </dd>
              </div>
            </dl>
            {belowMin && (
              <div className="alert-error space-y-2">
                <p>
                  Graded tasks ({graded}) below min ({MIN_GRADED}). Oracle
                  coverage is thin — metrics will be gold-free / assertion-weak.
                </p>
                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={ackGoldFree}
                    onChange={(e) => setAckGoldFree(e.target.checked)}
                  />
                  Run gold-free probe anyway
                </label>
              </div>
            )}
          </div>

          <div className="panel space-y-3">
            <h2 className="text-lg font-medium">Workspace files</h2>
            {previewables.length === 0 ? (
              <p className="text-sm" style={{ color: "var(--muted)" }}>
                No previewable artifacts.
              </p>
            ) : (
              <ul className="list-rows">
                {previewables.slice(0, 20).map((a) => (
                  <li key={a.name}>
                    <span className="font-mono text-sm">{a.name}</span>
                    <button
                      type="button"
                      className="btn btn-ghost"
                      style={{ padding: "0.35rem 0.7rem" }}
                      onClick={() => void onPreview(a.name)}
                    >
                      Preview
                    </button>
                  </li>
                ))}
              </ul>
            )}
            {previewName && (
              <div className="space-y-2">
                <p className="font-mono text-xs" style={{ color: "var(--muted)" }}>
                  {previewName}
                </p>
                <pre className="artifact-preview">
                  {previewText ?? "Loading…"}
                </pre>
              </div>
            )}
          </div>

          <div className="cta-row">
            <button
              type="button"
              className="btn btn-primary"
              disabled={busy || (belowMin && !ackGoldFree)}
              onClick={() => void onCreateExperiment()}
            >
              {busy ? "Creating…" : "Create experiment"}
            </button>
            <button
              type="button"
              className="btn btn-ghost"
              onClick={() => setStep("Staging")}
            >
              Reconfigure
            </button>
          </div>
        </div>
      )}

      {step === "Experiment" && (
        <p className="text-sm" style={{ color: "var(--muted)" }}>
          Redirecting to experiment detail…
        </p>
      )}
    </div>
  );
}
