"use client";

import { useEffect, useMemo, useState, type FormEvent } from "react";
import { ArmsMatrix } from "@/components/ArmsMatrix";
import { RefusalPanel } from "@/components/RefusalPanel";
import { SearchSelect } from "@/components/SearchSelect";
import { compareRuns, listRuns } from "@/lib/api";
import type { CompareResult, RunSummary } from "@/lib/types";

export default function ComparePage() {
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [runIds, setRunIds] = useState<string[]>([]);
  const [result, setResult] = useState<CompareResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    void listRuns()
      .then(setRuns)
      .catch((e: Error) => setError(e.message));
  }, []);

  const options = useMemo(
    () =>
      runs.map((r) => ({
        id: r.id,
        label: r.status,
        hint: [r.model, r.finishedAt ?? r.startedAt].filter(Boolean).join(" · ") || undefined,
      })),
    [runs],
  );

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (runIds.length < 2) {
      setError("Select at least two runs.");
      return;
    }
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      setResult(await compareRuns(runIds));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <header>
        <p className="section-label">Pooling</p>
        <h1 className="page-title">Compare</h1>
        <p className="page-lede">
          Diff N finished runs: setup deltas and what they changed. Exit 3
          (REFUSING TO POOL) is a first-class panel — never a toast or empty
          table. Different models refuse by default (hold model fixed for
          packaging claims).
        </p>
      </header>

      <form onSubmit={onSubmit} className="panel space-y-3">
        <div className="field-label">
          Runs
          <SearchSelect
            multiple
            options={options}
            value={runIds}
            onChange={setRunIds}
            placeholder="Search runs…"
            disabled={busy}
          />
        </div>
        <p className="text-xs" style={{ color: "var(--muted)" }}>
          {runIds.length === 0
            ? "Pick two or more runs from the catalog."
            : `${runIds.length} selected`}
        </p>
        <button type="submit" disabled={busy} className="btn btn-primary">
          Compare
        </button>
      </form>

      {error && <p className="alert-error">{error}</p>}

      {result?.refused && result.refusalText && (
        <RefusalPanel
          refusalText={result.refusalText}
          brokenBoundary={result.brokenBoundary}
        />
      )}

      {result && !result.refused && (
        <section className="panel">
          <p className="section-label">Result</p>
          <h2 className="page-title" style={{ fontSize: "1.5rem" }}>
            Compare output
          </h2>
          {result.artifactDir && (
            <p className="mt-1 font-mono text-xs" style={{ color: "var(--muted)" }}>
              {result.artifactDir}
            </p>
          )}
          <pre className="mt-3 overflow-x-auto whitespace-pre-wrap font-mono text-sm">
            {result.stdout || "(empty stdout)"}
          </pre>
        </section>
      )}

      <ArmsMatrix />
    </div>
  );
}
