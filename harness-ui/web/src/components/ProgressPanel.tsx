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
    <section className="border border-zinc-300 bg-white p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="font-semibold text-zinc-900">Progress</h2>
        <span className="font-mono text-sm text-zinc-700">
          {job.status}
          {terminal ? " · terminal" : ""}
        </span>
      </div>
      {progress && (
        <>
          <div className="mt-3 h-2 w-full bg-zinc-200">
            <div
              className="h-2 bg-zinc-800 transition-all"
              style={{ width: `${pct ?? 0}%` }}
            />
          </div>
          <p className="mt-2 text-sm text-zinc-700">
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
            <ul className="mt-2 grid grid-cols-2 gap-1 text-xs text-zinc-600 sm:grid-cols-4">
              {Object.entries(progress.by_arm).map(([arm, n]) => (
                <li key={arm} className="font-mono">
                  {arm}: {n}
                </li>
              ))}
            </ul>
          )}
        </>
      )}
      {job.message && (
        <p className="mt-2 text-sm text-red-800">{job.message}</p>
      )}
    </section>
  );
}
