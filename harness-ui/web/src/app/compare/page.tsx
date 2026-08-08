"use client";

import { useMemo, useState, type FormEvent } from "react";
import { RefusalPanel } from "@/components/RefusalPanel";
import { compareRuns } from "@/lib/api";
import type { CompareResult } from "@/lib/types";

export default function ComparePage() {
  const [runIdsText, setRunIdsText] = useState("smoke-demo, other-model");
  const [result, setResult] = useState<CompareResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const runIds = useMemo(
    () =>
      runIdsText
        .split(/[,\s]+/)
        .map((s) => s.trim())
        .filter(Boolean),
    [runIdsText],
  );

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (runIds.length < 2) {
      setError("Enter at least two run ids.");
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
        <h1 className="text-xl font-semibold text-zinc-900">Compare</h1>
        <p className="mt-1 text-sm text-zinc-600">
          Diff N runs. Exit 3 (REFUSING TO POOL) is a first-class panel — never
          a toast or empty table.
        </p>
      </header>

      <form
        onSubmit={onSubmit}
        className="space-y-3 border border-zinc-300 bg-white p-4"
      >
        <label className="block text-sm">
          <span className="text-zinc-600">Run ids (comma-separated)</span>
          <input
            className="mt-1 w-full border border-zinc-300 px-2 py-1.5 font-mono text-sm"
            value={runIdsText}
            onChange={(e) => setRunIdsText(e.target.value)}
          />
        </label>
        <p className="text-xs text-zinc-500">
          Mock: include <code className="font-mono">other-model</code> or{" "}
          <code className="font-mono">refuse</code> in an id to trigger pooling
          refusal.
        </p>
        <button
          type="submit"
          disabled={busy}
          className="border border-zinc-800 bg-zinc-900 px-3 py-1.5 text-sm text-white"
        >
          Compare
        </button>
      </form>

      {error && (
        <p className="border border-red-300 bg-red-50 p-3 text-sm text-red-900">
          {error}
        </p>
      )}

      {result?.refused && result.refusalText && (
        <RefusalPanel
          refusalText={result.refusalText}
          brokenBoundary={result.brokenBoundary}
        />
      )}

      {result && !result.refused && (
        <section className="border border-zinc-300 bg-white p-4">
          <h2 className="font-semibold text-zinc-900">Compare result</h2>
          {result.artifactDir && (
            <p className="mt-1 font-mono text-xs text-zinc-500">
              {result.artifactDir}
            </p>
          )}
          <pre className="mt-3 overflow-x-auto whitespace-pre-wrap font-mono text-sm text-zinc-800">
            {result.stdout || "(empty stdout)"}
          </pre>
        </section>
      )}
    </div>
  );
}
