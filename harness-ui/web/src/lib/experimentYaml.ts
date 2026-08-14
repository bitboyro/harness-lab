import type { ExperimentPlanDefaults } from "./types";

/** Escape a string for a double-quoted YAML value. */
function q(s: string): string {
  return JSON.stringify(s);
}

/** Fold prose into a YAML `>` block scalar. */
function foldBlock(text: string, indent: string): string {
  const trimmed = text.trim();
  if (!trimmed.includes("\n") && trimmed.length < 72) {
    return `${indent}${q(trimmed)}`;
  }
  const lines = trimmed.replace(/\s+/g, " ").match(/.{1,76}(\s|$)/g) ?? [trimmed];
  return `${indent}>\n${lines.map((l) => `${indent}  ${l.trim()}`).join("\n")}`;
}

export function buildExperimentYaml(plan: ExperimentPlanDefaults): string {
  const now = new Date().toISOString().replace(/\.\d{3}Z$/, "Z");
  const presetLines = plan.presets.map((p) => `      - ${p}`).join("\n");
  const slices =
    plan.includeSmokeSlice && plan.presets.length >= 2
      ? `
  slices:
    smoke:
      description: Two cores — pipeline check without full cost
      arms: [${plan.presets.slice(0, 3).join(", ")}]
      cores: 2`
      : "";

  return `schema_version: 1

experiment:
  id: ${q(plan.experimentId)}
  status: draft
  created_at: ${q(now)}
  updated_at: ${q(now)}
  llm_provider: ${q(plan.provider || "openai")}

  run_plan:
    id: ${q(plan.experimentId)}
    rationale: ${foldBlock(plan.rationale, "      ")}
    base:
      model: ${q(plan.model)}
      reasoning_effort: ${plan.reasoningEffort}
      temperature: 0.0
      caching: "off"
      repeats: ${plan.repeats}
      surface_size: ${plan.surfaceSize}
      schema_detail: standard
      response_shape: as-is
      error_detail: field-scoped
      doc_budget: standard
      mcp_revision: ${q(plan.mcpRevision)}
    include:
      presets:
${presetLines}
    tasks:
      generate: {seed: ${plan.seed}, cores: ${plan.cores}, fan_out: ${plan.fanOut}, difficulty: ${plan.difficulty}}
    budget: {max_usd: ${plan.maxUsd}}${slices}

  retired_arms: []
  episodes: []
  report_snapshots: []
`;
}
