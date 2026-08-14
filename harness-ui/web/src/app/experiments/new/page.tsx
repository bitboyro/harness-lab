"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";

import { FieldSelect } from "@/components/FieldSelect";
import { PresetPicker } from "@/components/PresetPicker";
import { createExperiment, getRunDefaults } from "@/lib/api";
import { buildExperimentYaml } from "@/lib/experimentYaml";
import type { ExperimentPlanDefaults, RunDefaultsConfig } from "@/lib/types";
import { modelsForProvider } from "@/lib/types";

export default function NewExperimentPage() {
  const router = useRouter();
  const [config, setConfig] = useState<RunDefaultsConfig | null>(null);
  const [templateId, setTemplateId] = useState("baseline-80");
  const [plan, setPlan] = useState<ExperimentPlanDefaults | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void getRunDefaults()
      .then((c) => {
        setConfig(c);
        const tpl = c.experimentTemplates[0];
        if (tpl) {
          setTemplateId(tpl.id);
          setPlan({ ...tpl.defaults });
        }
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  function applyTemplate(id: string) {
    if (!config) return;
    const tpl = config.experimentTemplates.find((t) => t.id === id);
    if (!tpl) return;
    setTemplateId(id);
    setPlan({ ...tpl.defaults });
  }

  function patch<K extends keyof ExperimentPlanDefaults>(
    key: K,
    value: ExperimentPlanDefaults[K],
  ) {
    setPlan((p) => (p ? { ...p, [key]: value } : p));
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!plan) return;
    if (plan.presets.length === 0) {
      setError("Select at least one preset arm.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const yaml = buildExperimentYaml(plan);
      await createExperiment({ id: plan.experimentId, yaml });
      router.push(`/experiments/${encodeURIComponent(plan.experimentId)}/`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  if (!plan || !config) {
    return (
      <div className="max-w-2xl">
        <p className="section-label">Experiments</p>
        <h1 className="page-title">New experiment</h1>
        {error ? (
          <p className="alert-error">{error}</p>
        ) : (
          <p className="text-sm" style={{ color: "var(--muted)" }}>
            Loading plan defaults…
          </p>
        )}
      </div>
    );
  }

  const needsSandbox = plan.presets.some((id) =>
    config.presets.find((p) => p.id === id)?.requiresSandbox,
  );

  return (
    <div className="max-w-2xl space-y-6">
      <div>
        <p className="section-label">Experiments</p>
        <h1 className="page-title">New experiment</h1>
        <p className="page-lede">
          Pick a template, tune the matrix, create the sidecar. Nothing spends
          until you approve a run on the detail page. Prefer uploading a customer
          OpenAPI? Use{" "}
          <Link href="/experiments/new/from-openapi/">From OpenAPI</Link>.
        </p>
      </div>
      {error && <p className="alert-error">{error}</p>}
      <form className="panel space-y-5" onSubmit={onSubmit}>
        <label className="field-label">
          Template
          <FieldSelect
            options={config.experimentTemplates.map((t) => ({
              id: t.id,
              label: t.label,
              hint: t.description,
            }))}
            value={templateId}
            onChange={applyTemplate}
          />
          <span className="mt-1 block text-xs" style={{ color: "var(--muted)" }}>
            {config.experimentTemplates.find((t) => t.id === templateId)?.description}
          </span>
        </label>

        <label className="field-label">
          Experiment id
          <input
            className="field-input"
            value={plan.experimentId}
            onChange={(e) => patch("experimentId", e.target.value)}
            required
          />
        </label>

        <label className="field-label">
          Rationale
          <textarea
            className="field-input min-h-[4rem]"
            value={plan.rationale}
            onChange={(e) => patch("rationale", e.target.value)}
            required
          />
        </label>

        <fieldset className="grid gap-3 sm:grid-cols-2">
          <legend className="mb-2 text-sm font-medium">Base axes</legend>
          <label className="field-label">
            Provider
            <FieldSelect
              options={
                config.providerProfiles?.map((p) => ({
                  id: p.id,
                  label: p.label,
                })) ?? config.providers
              }
              value={plan.provider ?? "openai"}
              onChange={(id) => {
                const models = modelsForProvider(config, id);
                patch("provider", id);
                if (!models.some((m) => m.id === plan.model) && models[0]) {
                  patch("model", models[0].id);
                }
              }}
            />
          </label>
          <label className="field-label">
            Model
            <FieldSelect
              options={modelsForProvider(config, plan.provider ?? "openai")}
              value={plan.model}
              onChange={(id) => patch("model", id)}
            />
          </label>
          {(
            [
              ["reasoningEffort", "Reasoning effort", config.reasoningEfforts],
              ["mcpRevision", "MCP revision", config.mcpRevisions],
            ] as const
          ).map(([key, label, options]) => (
            <label key={key} className="field-label">
              {label}
              <FieldSelect
                options={options}
                value={plan[key]}
                onChange={(id) => patch(key, id)}
              />
            </label>
          ))}
          <label className="field-label">
            Repeats
            <input
              type="number"
              min={1}
              className="field-input"
              value={plan.repeats}
              onChange={(e) => patch("repeats", Number(e.target.value) || 1)}
            />
          </label>
          <label className="field-label">
            Surface size
            <input
              type="number"
              min={1}
              className="field-input"
              value={plan.surfaceSize}
              onChange={(e) => patch("surfaceSize", Number(e.target.value) || 50)}
            />
          </label>
        </fieldset>

        <div>
          <p className="mb-2 text-sm font-medium">Preset arms</p>
          <PresetPicker
            presets={config.presets}
            selected={plan.presets}
            bundles={config.presetBundles}
            onChange={(presets) => patch("presets", presets)}
          />
          {needsSandbox && (
            <p className="mt-2 text-xs" style={{ color: "var(--muted)" }}>
              D arms selected — runs will need code sandbox enabled.
            </p>
          )}
        </div>

        <fieldset className="grid gap-3 sm:grid-cols-2">
          <legend className="mb-2 text-sm font-medium">Task generation</legend>
          <label className="field-label">
            Cores
            <input
              type="number"
              min={1}
              className="field-input"
              value={plan.cores}
              onChange={(e) => patch("cores", Number(e.target.value) || 1)}
            />
          </label>
          <label className="field-label">
            Fan-out
            <input
              type="number"
              min={1}
              className="field-input"
              value={plan.fanOut}
              onChange={(e) => patch("fanOut", Number(e.target.value) || 1)}
            />
          </label>
          <label className="field-label">
            Seed
            <input
              type="number"
              min={0}
              className="field-input"
              value={plan.seed}
              onChange={(e) => patch("seed", Number(e.target.value) || 0)}
            />
          </label>
          <label className="field-label">
            Difficulty
            <FieldSelect
              options={config.difficulties}
              value={plan.difficulty}
              onChange={(id) => patch("difficulty", id)}
            />
          </label>
          <label className="field-label sm:col-span-2">
            Budget cap (USD)
            <input
              type="number"
              min={1}
              className="field-input"
              value={plan.maxUsd}
              onChange={(e) => patch("maxUsd", Number(e.target.value) || 1)}
            />
          </label>
        </fieldset>

        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={plan.includeSmokeSlice}
            onChange={(e) => patch("includeSmokeSlice", e.target.checked)}
          />
          Include smoke slice (2 cores, first three arms)
        </label>

        <div className="cta-row">
          <button type="submit" className="btn btn-primary" disabled={busy}>
            {busy ? "Creating…" : "Create sidecar"}
          </button>
          <Link href="/experiments/" className="btn btn-ghost">
            Cancel
          </Link>
        </div>
      </form>
    </div>
  );
}
