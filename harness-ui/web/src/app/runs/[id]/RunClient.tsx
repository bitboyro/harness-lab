"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { AnalysisPanels } from "@/components/AnalysisPanels";
import { DeleteButton } from "@/components/DeleteButton";
import { ProgressPanel } from "@/components/ProgressPanel";
import { ReportSummary } from "@/components/ReportSummary";
import { TranscriptViewer } from "@/components/TranscriptViewer";
import {
  cacheReportOffline,
  deleteRun,
  getAnalysis,
  getReport,
  getRunProgress,
} from "@/lib/api";
import { usePathId } from "@/lib/pathId";
import type {
  AdapterAnalysis,
  AdapterReport,
  ProgressEnvelope,
} from "@/lib/types";

export function RunClient({ id: bakedId }: { id: string }) {
  const router = useRouter();
  const id = usePathId("runs") || bakedId;
  const [envelope, setEnvelope] = useState<ProgressEnvelope | null>(null);
  const [report, setReport] = useState<AdapterReport | null>(null);
  const [analysis, setAnalysis] = useState<AdapterAnalysis | null>(null);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!id || id === "_") return;
    let cancelled = false;

    async function loadReport() {
      try {
        const r = await getReport(id);
        if (cancelled) return;
        setReport(r);
        cacheReportOffline(id, r);
      } catch (e) {
        if (!cancelled) {
          console.debug("report not ready", e);
        }
      }
    }

    async function loadAnalysis() {
      try {
        const a = await getAnalysis(id);
        if (!cancelled) setAnalysis(a);
      } catch (e) {
        if (!cancelled) console.debug("analysis not ready", e);
      }
    }

    async function onTerminal() {
      await loadReport();
      await loadAnalysis();
    }

    async function tick() {
      try {
        const env = await getRunProgress(id);
        if (cancelled) return;
        setError(null);
        setEnvelope(env);
        if (env.terminal) {
          if (pollRef.current) {
            clearInterval(pollRef.current);
            pollRef.current = null;
          }
          await onTerminal();
        }
      } catch (e) {
        if (cancelled) return;
        try {
          const r = await getReport(id);
          if (!cancelled) {
            setReport(r);
            cacheReportOffline(id, r);
            setError(null);
          }
          await loadAnalysis();
        } catch {
          if (!cancelled) {
            setError(e instanceof Error ? e.message : String(e));
          }
        }
        if (pollRef.current) {
          clearInterval(pollRef.current);
          pollRef.current = null;
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

  if (!id || id === "_") {
    return (
      <p className="text-sm" style={{ color: "var(--muted)" }}>
        Missing run id in the URL.{" "}
        <Link href="/" className="btn btn-ghost" style={{ padding: "0.2rem 0.4rem" }}>
          Home
        </Link>
      </p>
    );
  }

  return (
    <div className="space-y-6">
      <header>
        <p className="section-label">
          <Link href="/">Home</Link>
          {" / "}
          <Link href="/runs/">runs</Link>
          {" / "}
          <span className="font-mono">{id}</span>
        </p>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h1 className="page-title">Run</h1>
          <DeleteButton
            label={id}
            onDelete={async () => {
              await deleteRun(id);
              router.push("/runs/");
            }}
          />
        </div>
      </header>

      {error && !report && <p className="alert-error">{error}</p>}

      {envelope && <ProgressPanel envelope={envelope} />}

      {report && <ReportSummary report={report} />}

      {analysis && <AnalysisPanels analysis={analysis} />}

      {report && <TranscriptViewer runId={id} />}

      {!report && !error && !envelope && (
        <p className="text-sm" style={{ color: "var(--muted)" }}>
          Loading…
        </p>
      )}
    </div>
  );
}
