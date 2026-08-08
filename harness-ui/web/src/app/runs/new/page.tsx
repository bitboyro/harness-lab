"use client";

import Link from "next/link";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { getRunProgress, projectRunCost, startRun } from "@/lib/api";
import { ProgressPanel } from "@/components/ProgressPanel";
import type { CostProjection, ProgressEnvelope, RunRequest } from "@/lib/types";

const DEFAULT: RunRequest = {
  id: "smoke-demo",
  packId: "demo",
  targetId: null,
  presets: ["A1", "Z0"],
  model: "gpt-4.1-mini",
  provider: "openai",
  reasoningEffort: "low",
  repeats: 1,
  smoke: true,
  probe: false,
  resume: false,
  dryRun: false,
  allowCodeSandbox: false,
};

export default function NewRunPage() {
  const [form, setForm] = useState<RunRequest>(DEFAULT);
  const [presetsText, setPresetsText] = useState(DEFAULT.presets.join(", "));
  const [projection, setProjection] = useState<CostProjection | null>(null);
  const [envelope, setEnvelope] = useState<ProgressEnvelope | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  function buildRequest(): RunRequest {
    const presets = presetsText
      .split(/[,\s]+/)
      .map((s) => s.trim())
      .filter(Boolean);
    return { ...form, presets };
  }

  async function onProject(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setProjection(null);
    try {
      setProjection(await projectRunCost(buildRequest()));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  function stopPolling() {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }

  async function onApprove() {
    setBusy(true);
    setError(null);
    try {
      const req = buildRequest();
      const job = await startRun({ ...req, approve: true });
      setEnvelope({
        job,
        progress: null,
        terminal: false,
      });
      stopPolling();
      pollRef.current = setInterval(() => {
        void getRunProgress(job.id)
          .then((env) => {
            setEnvelope(env);
            if (env.terminal) stopPolling();
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

  function field<K extends keyof RunRequest>(key: K, value: RunRequest[K]) {
    setForm((f) => ({ ...f, [key]: value }));
    setProjection(null);
  }

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-xl font-semibold text-zinc-900">New run</h1>
        <p className="mt-1 text-sm text-zinc-600">
          Project cost → approve → start. Progress polling stops when the job is
          terminal.
        </p>
      </header>

      {error && (
        <p className="border border-red-300 bg-red-50 p-3 text-sm text-red-900">
          {error}
        </p>
      )}

      <form
        onSubmit={onProject}
        className="grid gap-3 border border-zinc-300 bg-white p-4 sm:grid-cols-2"
      >
        {(
          [
            ["id", "Run id"],
            ["packId", "Pack id"],
            ["targetId", "Target id"],
            ["model", "Model"],
            ["provider", "Provider"],
            ["reasoningEffort", "Reasoning effort"],
          ] as const
        ).map(([key, label]) => (
          <label key={key} className="block text-sm">
            <span className="text-zinc-600">{label}</span>
            <input
              className="mt-1 w-full border border-zinc-300 px-2 py-1.5 font-mono text-sm"
              value={String(form[key] ?? "")}
              onChange={(e) =>
                field(
                  key,
                  (e.target.value === "" &&
                  (key === "packId" || key === "targetId")
                    ? null
                    : e.target.value) as RunRequest[typeof key],
                )
              }
            />
          </label>
        ))}

        <label className="block text-sm sm:col-span-2">
          <span className="text-zinc-600">Presets (comma-separated)</span>
          <input
            className="mt-1 w-full border border-zinc-300 px-2 py-1.5 font-mono text-sm"
            value={presetsText}
            onChange={(e) => {
              setPresetsText(e.target.value);
              setProjection(null);
            }}
          />
        </label>

        <label className="block text-sm">
          <span className="text-zinc-600">Repeats</span>
          <input
            type="number"
            min={1}
            className="mt-1 w-full border border-zinc-300 px-2 py-1.5 font-mono text-sm"
            value={form.repeats}
            onChange={(e) => field("repeats", Number(e.target.value) || 1)}
          />
        </label>

        <div className="flex flex-wrap gap-4 text-sm sm:col-span-2">
          {(
            [
              ["smoke", "Smoke"],
              ["probe", "Probe"],
              ["resume", "Resume"],
              ["allowCodeSandbox", "Allow code sandbox (D arms)"],
            ] as const
          ).map(([key, label]) => (
            <label key={key} className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={Boolean(form[key])}
                onChange={(e) => field(key, e.target.checked)}
              />
              {label}
            </label>
          ))}
        </div>

        <div className="sm:col-span-2">
          <button
            type="submit"
            disabled={busy}
            className="border border-zinc-800 bg-zinc-900 px-3 py-1.5 text-sm text-white"
          >
            Project cost
          </button>
        </div>
      </form>

      {projection && (
        <section className="border border-zinc-300 bg-white p-4">
          <h2 className="font-semibold text-zinc-900">Cost projection</h2>
          <pre className="mt-2 whitespace-pre-wrap font-mono text-sm text-zinc-800">
            {projection.projectionText}
          </pre>
          <p className="mt-2 text-xs text-zinc-500">
            exitCode={projection.exitCode}
            {projection.stderrNames.length
              ? ` · env: ${projection.stderrNames.join(", ")}`
              : ""}
          </p>
          <button
            type="button"
            disabled={busy}
            onClick={() => void onApprove()}
            className="mt-3 border border-emerald-900 bg-emerald-900 px-3 py-1.5 text-sm text-white"
          >
            Approve &amp; start
          </button>
        </section>
      )}

      {envelope && (
        <div className="space-y-3">
          <ProgressPanel envelope={envelope} />
          {envelope.terminal && (
            <p className="text-sm">
              Terminal ({envelope.job.status}).{" "}
              <Link
                href={`/runs/${encodeURIComponent(envelope.job.id)}/`}
                className="underline"
              >
                Open run report
              </Link>
            </p>
          )}
        </div>
      )}
    </div>
  );
}
