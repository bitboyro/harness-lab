"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";

import { FieldSelect } from "@/components/FieldSelect";
import { PresetPicker } from "@/components/PresetPicker";
import { ProgressPanel } from "@/components/ProgressPanel";
import { SearchSelect } from "@/components/SearchSelect";
import {
  getRunDefaults,
  getRunProgress,
  listPacks,
  listTargets,
  projectRunCost,
  startRun,
} from "@/lib/api";
import type { CostProjection, ProgressEnvelope, RunDefaultsConfig, RunRequest } from "@/lib/types";
import { modelsForProvider } from "@/lib/types";

type Props = {
  onRunsChange?: () => void;
};

export function NewRunForm({ onRunsChange }: Props) {
  const [config, setConfig] = useState<RunDefaultsConfig | null>(null);
  const [form, setForm] = useState<RunRequest | null>(null);
  const [targets, setTargets] = useState<{ id: string; label: string; hint?: string }[]>([]);
  const [packs, setPacks] = useState<{ id: string; label?: string; hint?: string }[]>([]);
  const [projection, setProjection] = useState<CostProjection | null>(null);
  const [envelope, setEnvelope] = useState<ProgressEnvelope | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    void Promise.all([getRunDefaults(), listTargets(), listPacks()])
      .then(([cfg, tgs, pks]) => {
        setConfig(cfg);
        setForm({ ...cfg.defaultRun });
        setTargets(tgs.map((t) => ({ id: t.id, label: t.label, hint: t.kind })));
        setPacks(
          pks.map((p) => ({
            id: p.id,
            hint: p.path,
            label: p.valid ? "valid" : "invalid",
          })),
        );
      })
      .catch((e: Error) => setError(e.message));
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  function field<K extends keyof RunRequest>(key: K, value: RunRequest[K]) {
    setForm((f) => (f ? { ...f, [key]: value } : f));
    setProjection(null);
  }

  function applyMode(mode: "smoke" | "probe" | "custom") {
    if (!config || !form) return;
    if (mode === "smoke") {
      setForm({
        ...form,
        smoke: true,
        probe: false,
        presets: [],
        repeats: 1,
        allowCodeSandbox: true,
      });
    } else if (mode === "probe") {
      setForm({
        ...form,
        smoke: false,
        probe: true,
        presets: [...(config.presetBundles.probe ?? [])],
        repeats: 1,
        resume: false,
        allowCodeSandbox: true,
      });
    } else {
      setForm({ ...form, smoke: false, probe: false });
    }
    setProjection(null);
  }

  async function onProject(e: FormEvent) {
    e.preventDefault();
    if (!form) return;
    setBusy(true);
    setError(null);
    setProjection(null);
    try {
      setProjection(await projectRunCost(form));
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
    if (!form) return;
    setBusy(true);
    setError(null);
    try {
      const job = await startRun({ ...form, approve: true });
      onRunsChange?.();
      setEnvelope({ job, progress: null, terminal: false });
      stopPolling();
      pollRef.current = setInterval(() => {
        void getRunProgress(job.id)
          .then((env) => {
            setEnvelope(env);
            if (env.terminal) {
              stopPolling();
              onRunsChange?.();
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

  if (!form || !config) {
    return (
      <p className="text-sm" style={{ color: "var(--muted)" }}>
        {error ? <span className="alert-error">{error}</span> : "Loading defaults…"}
      </p>
    );
  }

  const needsSandbox = form.presets.some((id) =>
    config.presets.find((p) => p.id === id)?.requiresSandbox,
  );

  return (
    <div className="space-y-4">
      {error && <p className="alert-error">{error}</p>}

      <form onSubmit={onProject} className="panel space-y-4">
        <div className="flex flex-wrap gap-2">
          {(
            [
              ["smoke", "Smoke (~$0.05)"],
              ["probe", "Field probe"],
              ["custom", "Custom"],
            ] as const
          ).map(([mode, label]) => (
            <button
              key={mode}
              type="button"
              className="btn btn-ghost"
              style={{ padding: "0.35rem 0.65rem", fontSize: "0.85rem" }}
              onClick={() => applyMode(mode)}
            >
              {label}
            </button>
          ))}
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          <label className="field-label">
            Run id
            <input
              className="field-input"
              value={form.id}
              onChange={(e) => field("id", e.target.value)}
              required
            />
          </label>
          <div className="field-label">
            Pack
            <SearchSelect
              options={packs}
              value={form.packId}
              onChange={(id) => field("packId", id)}
              placeholder="Search packs… (empty → controlled)"
              emptyLabel="— controlled smoke —"
              allowClear
            />
          </div>
          <div className="field-label">
            Target
            <SearchSelect
              options={targets}
              value={form.targetId}
              onChange={(id) => field("targetId", id)}
              placeholder="Search targets…"
              emptyLabel="— none —"
              allowClear
            />
          </div>
          <label className="field-label">
            Provider
            <FieldSelect
              options={
                config.providerProfiles?.map((p) => ({
                  id: p.id,
                  label: p.label,
                  hint: p.adapter !== p.id ? p.adapter : undefined,
                })) ?? config.providers
              }
              value={form.provider}
              onChange={(id) => {
                const models = modelsForProvider(config, id);
                const model =
                  models.some((m) => m.id === form.model)
                    ? form.model
                    : (models[0]?.id ?? form.model);
                setForm((f) => (f ? { ...f, provider: id, model } : f));
                setProjection(null);
              }}
            />
          </label>
          <label className="field-label">
            Model
            <FieldSelect
              options={modelsForProvider(config, form.provider)}
              value={form.model}
              onChange={(id) => field("model", id)}
            />
          </label>
          <label className="field-label">
            Reasoning effort
            <FieldSelect
              options={config.reasoningEfforts}
              value={form.reasoningEffort}
              onChange={(id) => field("reasoningEffort", id)}
            />
          </label>
          <label className="field-label">
            Repeats
            <input
              type="number"
              min={1}
              className="field-input"
              value={form.repeats}
              onChange={(e) => field("repeats", Number(e.target.value) || 1)}
            />
          </label>
        </div>

        {!form.smoke && (
          <div>
            <p className="mb-2 text-sm font-medium">Presets</p>
            <PresetPicker
              presets={config.presets}
              selected={form.presets}
              bundles={config.presetBundles}
              onChange={(presets) => field("presets", presets)}
            />
          </div>
        )}

        <div className="flex flex-wrap gap-4 text-sm" style={{ color: "var(--ink-soft)" }}>
          {(
            [
              ["smoke", "Smoke matrix"],
              ["probe", "Probe profile"],
              ["resume", "Resume ledger"],
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

        {needsSandbox && !form.allowCodeSandbox && (
          <p className="text-sm" style={{ color: "var(--signal)" }}>
            D presets selected — enable code sandbox or remove D arms.
          </p>
        )}

        <button type="submit" disabled={busy} className="btn btn-primary">
          Project cost
        </button>
      </form>

      {projection && (
        <section className="panel panel-ink">
          <p className="section-label">Projection</p>
          <h2 className="page-title" style={{ color: "var(--fog)", fontSize: "1.5rem" }}>
            Cost before spend
          </h2>
          <pre className="mt-3 whitespace-pre-wrap font-mono text-sm" style={{ color: "var(--fog)" }}>
            {projection.projectionText}
          </pre>
          <button
            type="button"
            disabled={busy || (needsSandbox && !form.allowCodeSandbox)}
            onClick={() => void onApprove()}
            className="btn btn-signal mt-4"
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
              <a
                href={`/runs/${encodeURIComponent(envelope.job.id)}/`}
                className="btn btn-ghost"
                style={{ padding: "0.2rem 0.4rem" }}
              >
                Open run report
              </a>
            </p>
          )}
        </div>
      )}
    </div>
  );
}
