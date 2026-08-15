"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { ArmChip } from "@/components/ArmChip";
import { DeleteButton } from "@/components/DeleteButton";
import { ProgressPanel } from "@/components/ProgressPanel";
import { ReportSummary } from "@/components/ReportSummary";
import { SearchSelect } from "@/components/SearchSelect";
import {
  addExperimentArms,
  deleteExperiment,
  getExperiment,
  getReport,
  getRunDefaults,
  getRunProgress,
  listExperimentReports,
  projectExperimentRun,
  snapshotExperimentReport,
  startExperimentRun,
} from "@/lib/api";
import { usePathId } from "@/lib/pathId";
import type {
  AdapterReport,
  ExperimentEnvelope,
  ExperimentRunProjection,
  PresetOption,
  ProgressEnvelope,
  ReportSnapshotRef,
} from "@/lib/types";

export function ExperimentClient({ id: bakedId }: { id: string }) {
  const router = useRouter();
  const id = usePathId("experiments") || bakedId;
  const [env, setEnv] = useState<ExperimentEnvelope | null>(null);
  const [report, setReport] = useState<AdapterReport | null>(null);
  const [projection, setProjection] = useState<ExperimentRunProjection | null>(null);
  const [envelope, setEnvelope] = useState<ProgressEnvelope | null>(null);
  const [snapshots, setSnapshots] = useState<ReportSnapshotRef[]>([]);
  const [presetsCatalog, setPresetsCatalog] = useState<PresetOption[]>([]);
  const [slice, setSlice] = useState("");
  const [pendingArms, setPendingArms] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    void getRunDefaults()
      .then((c) => setPresetsCatalog(c.presets ?? []))
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    if (!id || id === "_") return;
    void reload();
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [id]);

  async function reload() {
    try {
      const data = await getExperiment(id, slice || undefined);
      setEnv(data);
      setError(null);
      try {
        setReport(await getReport(id));
      } catch {
        setReport(null);
      }
      try {
        setSnapshots(await listExperimentReports(id));
      } catch {
        setSnapshots([]);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  async function onProject() {
    setBusy(true);
    setError(null);
    try {
      setProjection(
        await projectExperimentRun(id, {
          slice: slice || null,
          allowCodeSandbox: true,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function onRun() {
    setBusy(true);
    setError(null);
    try {
      const job = await startExperimentRun(id, {
        slice: slice || null,
        approve: true,
        allowCodeSandbox: true,
      });
      setEnvelope({ job, progress: null, terminal: false });
      if (pollRef.current) clearInterval(pollRef.current);
      pollRef.current = setInterval(() => {
        void getRunProgress(id)
          .then((env) => {
            setEnvelope(env);
            if (env.terminal) {
              if (pollRef.current) clearInterval(pollRef.current);
              void reload();
            }
          })
          .catch((e: Error) => setError(e.message));
      }, 800);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function onAddArms() {
    if (!pendingArms.length) return;
    setBusy(true);
    try {
      await addExperimentArms(id, pendingArms);
      setPendingArms([]);
      await reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function onSnapshot() {
    setBusy(true);
    try {
      await snapshotExperimentReport(id);
      setSnapshots(await listExperimentReports(id));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  if (!id || id === "_") return null;

  const cov = env?.coverage;
  const slices = env?.experiment.slices ?? {};
  const presets = env?.experiment.run_plan?.include?.presets ?? [];

  return (
    <div className="space-y-8">
      <div>
        <p className="section-label">
          <Link href="/">Home</Link>
          {" / "}
          <Link href="/experiments/">experiments</Link>
          {" / "}
          <span className="font-mono">{id}</span>
        </p>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h1 className="page-title font-mono">{id}</h1>
          <DeleteButton
            label={id}
            onDelete={async () => {
              await deleteExperiment(id);
              router.push("/experiments/");
            }}
          />
        </div>
        {env && (
          <p className="page-lede">
            status={env.experiment.status}
            {cov?.complete_fraction != null
              ? ` · ${Math.round(cov.complete_fraction * 100)}% complete`
              : ""}
            {" · "}
            {cov?.missing_cells ?? "—"} missing cells
          </p>
        )}
      </div>

      {error && <p className="alert-error">{error}</p>}

      <section className="panel space-y-3">
        <h2 className="text-lg font-medium">Coverage</h2>
        {cov && (
          <div className="grid gap-2 text-sm font-mono">
            {Object.entries(cov.by_arm).map(([arm, s]) => (
              <div key={arm} className="flex justify-between gap-4">
                <span>{arm}</span>
                <span style={{ color: "var(--muted)" }}>
                  {s.done}/{s.expected}
                  {s.missing ? ` (${s.missing} missing)` : ""}
                </span>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="panel space-y-3">
        <h2 className="text-lg font-medium">Run missing cells</h2>
        <div className="field-label">
          Slice
          <SearchSelect
            options={Object.entries(slices).map(([k, s]) => ({
              id: k,
              label: s.description ?? k,
            }))}
            value={slice || null}
            onChange={(id) => setSlice(id ?? "")}
            placeholder="Search slices…"
            emptyLabel="Full declared set"
            allowClear
            disabled={busy}
          />
        </div>
        <div className="cta-row">
          <button type="button" className="btn btn-ghost" disabled={busy} onClick={onProject}>
            Project cost
          </button>
          <button type="button" className="btn btn-primary" disabled={busy} onClick={onRun}>
            Fill gaps
          </button>
          <Link href={`/runs/${encodeURIComponent(id)}/`} className="btn btn-ghost">
            Run detail
          </Link>
        </div>
        {projection && (
          <pre className="whitespace-pre-wrap text-sm font-mono" style={{ color: "var(--muted)" }}>
            {projection.projectionText}
            {"\n\n"}
            missing: {projection.missingCells} · voided: {projection.voidedCells}
          </pre>
        )}
        {envelope && <ProgressPanel envelope={envelope} />}
      </section>

      <section className="panel space-y-3">
        <h2 className="text-lg font-medium">Add arms</h2>
        <p className="text-sm" style={{ color: "var(--muted)" }}>
          Declared:{" "}
          {presets.length === 0
            ? "—"
            : presets.map((p) => (
                <span key={p} className="mr-2 inline-block">
                  <ArmChip arm={p} />
                </span>
              ))}
        </p>
        <div className="space-y-2">
          <div className="field-label">
            Arms to add
            <SearchSelect
              multiple
              options={presetsCatalog
                .filter((p) => !presets.includes(p.id))
                .map((p) => ({
                  id: p.id,
                  label: p.label,
                  hint: p.description,
                }))}
              value={pendingArms}
              onChange={setPendingArms}
              placeholder="Search arms…"
              disabled={busy}
            />
          </div>
          <button type="button" className="btn btn-ghost" disabled={busy} onClick={onAddArms}>
            Add
          </button>
        </div>
      </section>

      {report && (
        <section className="panel">
          <ReportSummary report={report} />
        </section>
      )}

      <section className="panel space-y-3">
        <div className="flex items-baseline justify-between">
          <h2 className="text-lg font-medium">Report snapshots</h2>
          <button type="button" className="btn btn-ghost" disabled={busy} onClick={onSnapshot}>
            Snapshot now
          </button>
        </div>
        {snapshots.length === 0 ? (
          <p className="text-sm" style={{ color: "var(--muted)" }}>
            No dated snapshots yet.
          </p>
        ) : (
          <ul className="list-rows">
            {snapshots.map((s) => (
              <li key={s.at}>
                <span className="font-mono text-sm">
                  {s.at} · {s.status} · {s.ledgerRows ?? 0} rows
                </span>
                <span className="text-sm" style={{ color: "var(--muted)" }}>
                  {s.path}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
