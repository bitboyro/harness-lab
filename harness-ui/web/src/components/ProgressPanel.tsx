import type { ProgressEnvelope } from "@/lib/types";

type Props = {
  envelope: ProgressEnvelope;
};

export function ProgressPanel({ envelope }: Props) {
  const { job, progress, terminal } = envelope;
  const fraction = progress?.fraction ?? null;
  const pct =
    fraction != null
      ? Math.round(fraction * 100)
      : progress && progress.expected
        ? Math.round((progress.done / progress.expected) * 100)
        : null;

  return (
    <section className="panel">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <p className="section-label">Live</p>
          <h2 className="page-title" style={{ fontSize: "1.5rem" }}>
            Progress
          </h2>
        </div>
        <span className="font-mono text-xs uppercase tracking-wider" style={{ color: "var(--muted)" }}>
          {job.status}
          {terminal ? " · terminal" : ""}
        </span>
      </div>
      {progress && (
        <>
          <div className="progress-track mt-4">
            <div
              className="progress-fill"
              style={{ width: `${pct ?? 0}%`, background: terminal ? "var(--signal)" : "var(--ink)" }}
            />
          </div>
          <p className="mt-2 text-sm" style={{ color: "var(--ink-soft)" }}>
            {progress.done}
            {progress.expected != null ? ` / ${progress.expected}` : ""} cells
            {pct != null ? ` (${pct}%)` : ""}
            {" · "}
            elapsed {Math.round(progress.elapsed_seconds)}s
            {progress.eta_seconds != null && !terminal
              ? ` · eta ~${Math.round(progress.eta_seconds)}s`
              : ""}
          </p>
          {Object.keys(progress.by_arm).length > 0 && (
            <ul className="mt-3 grid grid-cols-2 gap-1 font-mono text-xs sm:grid-cols-4" style={{ color: "var(--muted)" }}>
              {Object.entries(progress.by_arm).map(([arm, n]) => (
                <li key={arm}>
                  {arm}: {n}
                </li>
              ))}
            </ul>
          )}
        </>
      )}
      {job.message && (
        <p className="alert-error mt-3">{job.message}</p>
      )}
    </section>
  );
}
