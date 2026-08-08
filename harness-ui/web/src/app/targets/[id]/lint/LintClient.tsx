"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { lintTarget } from "@/lib/api";
import type { AdapterLint } from "@/lib/types";

export function LintClient({ id }: { id: string }) {
  const [lint, setLint] = useState<AdapterLint | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void lintTarget(id)
      .then(setLint)
      .catch((e: Error) => setError(e.message));
  }, [id]);

  return (
    <div className="space-y-4">
      <header>
        <p className="text-sm text-zinc-500">
          <Link href="/targets/" className="underline">
            Targets
          </Link>
          {" / "}
          <span className="font-mono">{id}</span>
          {" / lint"}
        </p>
        <h1 className="mt-1 text-xl font-semibold text-zinc-900">Lint</h1>
      </header>

      {error && (
        <p className="border border-red-300 bg-red-50 p-3 text-sm text-red-900">
          {error}
        </p>
      )}

      {!lint && !error && (
        <p className="text-sm text-zinc-500">Running lint…</p>
      )}

      {lint && (
        <>
          <div className="overflow-x-auto border border-zinc-300 bg-white">
            <table className="w-full min-w-[40rem] text-left text-sm">
              <thead className="border-b border-zinc-300 bg-zinc-50 text-xs uppercase tracking-wide text-zinc-600">
                <tr>
                  <th className="px-3 py-2">Rule</th>
                  <th className="px-3 py-2">Severity</th>
                  <th className="px-3 py-2">Confidence</th>
                  <th className="px-3 py-2">Message</th>
                  <th className="px-3 py-2">Location</th>
                </tr>
              </thead>
              <tbody>
                {lint.findings.map((f, i) => (
                  <tr
                    key={`${f.rule_id}-${i}`}
                    className="border-b border-zinc-200"
                  >
                    <td className="px-3 py-2 font-mono">{f.rule_id}</td>
                    <td className="px-3 py-2">{f.severity}</td>
                    <td className="px-3 py-2">{f.confidence}</td>
                    <td className="px-3 py-2">{f.message}</td>
                    <td className="px-3 py-2 font-mono text-xs text-zinc-600">
                      {f.location ?? "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <footer className="border border-zinc-300 bg-zinc-50 p-3 font-mono text-xs text-zinc-700">
            {lint.footer}
            <div className="mt-1 text-zinc-500">
              rules_run={lint.rules_run} · rules_measured={lint.rules_measured}{" "}
              · measured_fraction={lint.measured_fraction.toFixed(3)} · harness{" "}
              {lint.harness_version}
            </div>
          </footer>
        </>
      )}
    </div>
  );
}
