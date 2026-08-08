/** IDs pre-rendered for `output: 'export'`. Mock mode uses these. */
export const TARGET_IDS = [
  "demo-openapi",
  "demo-mcp",
  "target-1",
  "target-2",
  "target-3",
  "_",
] as const;

export const PACK_IDS = ["demo", "demo-pack", "_"] as const;

export const RUN_IDS = [
  "smoke-demo",
  "smoke",
  "run-1",
  "run-2",
  "other-model",
  "_",
] as const;

export const ARTIFACT_NAMES = ["report.html", "summary.json", "_"] as const;
