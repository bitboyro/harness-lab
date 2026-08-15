"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { lintTarget } from "@/lib/api";
import { usePathId } from "@/lib/pathId";
import type { AdapterLint } from "@/lib/types";

export function LintClient({ id: bakedId }: { id: string }) {
  const id = usePathId("targets") || bakedId;
  const [lint, setLint] = useState<AdapterLint | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id || id === "_") return;
    void lintTarget(id)
      .then(setLint)
      .catch((e: Error) => setError(e.message));
  }, [id]);

  return (
    <div className="space-y-4">
      <header>
        <p className="section-label">
          <Link href="/targets/">Targets</Link>
          {" / "}
          <span className="font-mono">{id}</span>
        </p>
        <h1 className="page-title">Lint</h1>
      </header>

      {error && <p className="alert-error">{error}</p>}

      {!lint && !error && (
        <p className="text-sm" style={{ color: "var(--muted)" }}>
          Running lint…
        </p>
      )}

      {lint && (
        <>
          <div className="panel overflow-x-auto !p-0">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Rule</th>
                  <th>Severity</th>
                  <th>Confidence</th>
                  <th>Message</th>
                  <th>Location</th>
                </tr>
              </thead>
              <tbody>
                {lint.findings.map((f, i) => (
                  <tr key={`${f.rule_id}-${i}`}>
                    <td className="font-mono">{f.rule_id}</td>
                    <td>{f.severity}</td>
                    <td>{f.confidence}</td>
                    <td>{f.message}</td>
                    <td className="font-mono text-xs" style={{ color: "var(--muted)" }}>
                      {f.location ?? "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <footer className="panel font-mono text-xs" style={{ color: "var(--muted)" }}>
            {lint.footer}
            <div className="mt-1">
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
