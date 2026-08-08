"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { ProgressPanel } from "@/components/ProgressPanel";
import { ReportSummary } from "@/components/ReportSummary";
import {
  cacheReportOffline,
  getReport,
  getRunProgress,
  listArtifacts,
} from "@/lib/api";
import type { AdapterReport, ArtifactRef, ProgressEnvelope } from "@/lib/types";

export function RunClient({ id }: { id: string }) {
  const [envelope, setEnvelope] = useState<ProgressEnvelope | null>(null);
  const [report, setReport] = useState<AdapterReport | null>(null);
  const [artifacts, setArtifacts] = useState<ArtifactRef[]>([]);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function loadReport() {
      try {
        const r = await getReport(id);
        if (cancelled) return;
        setReport(r);
        cacheReportOffline(id, r);
      } catch {
        if (!cancelled) {
          /* report may not exist until terminal */
        }
      }
    }

    async function tick() {
      try {
        const env = await getRunProgress(id);
        if (cancelled) return;
        setEnvelope(env);
        if (env.terminal) {
          if (pollRef.current) {
            clearInterval(pollRef.current);
            pollRef.current = null;
          }
          await loadReport();
          try {
            setArtifacts(await listArtifacts(id));
          } catch {
            /* optional */
          }
        }
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : String(e));
          if (pollRef.current) {
            clearInterval(pollRef.current);
            pollRef.current = null;
          }
        }
      }
    }

    void tick();
    pollRef.current = setInterval(() => void tick(), 1000);

    return () => {
      cancelled = true;
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [id]);

  return (
    <div className="space-y-6">
      <header>
        <p className="text-sm text-zinc-500">
          <Link href="/" className="underline">
            Home
          </Link>
          {" / runs / "}
          <span className="font-mono">{id}</span>
        </p>
        <h1 className="mt-1 text-xl font-semibold text-zinc-900">Run</h1>
      </header>

      {error && (
        <p className="border border-red-300 bg-red-50 p-3 text-sm text-red-900">
          {error}
        </p>
      )}

      {envelope && <ProgressPanel envelope={envelope} />}

      {report && <ReportSummary report={report} />}

      {artifacts.length > 0 && (
        <section>
          <h2 className="mb-2 font-semibold text-zinc-900">Artifacts</h2>
          <ul className="divide-y divide-zinc-200 border border-zinc-300 bg-white text-sm">
            {artifacts.map((a) => (
              <li key={a.name} className="px-3 py-2">
                <Link
                  href={`/runs/${encodeURIComponent(id)}/artifacts/${encodeURIComponent(a.name)}/`}
                  className="font-mono underline"
                >
                  {a.name}
                </Link>
                {a.contentType && (
                  <span className="ml-2 text-zinc-500">{a.contentType}</span>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
