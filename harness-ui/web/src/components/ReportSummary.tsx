import type { AdapterReport } from "@/lib/types";

type Props = {
  report: AdapterReport;
};

function fmt(n: number | null | undefined, digits = 2): string {
  if (n == null || Number.isNaN(n)) return "—";
  return n.toFixed(digits);
}

export function ReportSummary({ report }: Props) {
  const arms = Object.values(report.arms).sort((a, b) => {
    const sa = a.composite_score ?? -Infinity;
    const sb = b.composite_score ?? -Infinity;
    return sb - sa;
  });

  return (
    <section className="space-y-4">
      <div className="border border-zinc-300 bg-white p-4">
        <h2 className="font-semibold text-zinc-900">Verdict</h2>
        <p className="mt-1 text-sm text-zinc-800">
          Winner:{" "}
          <span className="font-mono font-semibold">
            {report.verdict.winner ?? "none"}
          </span>
        </p>
        <p className="mt-1 text-sm text-zinc-700">{report.verdict.reason}</p>
        {report.verdict.caveats.length > 0 && (
          <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-amber-950">
            {report.verdict.caveats.map((c) => (
              <li key={c}>{c}</li>
            ))}
          </ul>
        )}
        <p className="mt-3 text-xs text-zinc-500">
          validation={report.validation} · model={report.run.model} · class=
          {report.run.report_class}
        </p>
      </div>

      <div className="overflow-x-auto border border-zinc-300 bg-white">
        <table className="w-full min-w-[36rem] text-left text-sm">
          <thead className="border-b border-zinc-300 bg-zinc-50 text-xs uppercase tracking-wide text-zinc-600">
            <tr>
              <th className="px-3 py-2">Arm</th>
              <th className="px-3 py-2">n</th>
              <th className="px-3 py-2">Success</th>
              <th className="px-3 py-2">Harm</th>
              <th className="px-3 py-2">Score</th>
              <th className="px-3 py-2">$/success</th>
              <th className="px-3 py-2">Control</th>
            </tr>
          </thead>
          <tbody>
            {arms.map((a) => (
              <tr key={a.arm} className="border-b border-zinc-200">
                <td className="px-3 py-2 font-mono">
                  {a.arm}
                  {a.name ? (
                    <span className="ml-2 text-zinc-500">{a.name}</span>
                  ) : null}
                </td>
                <td className="px-3 py-2 font-mono">{a.n}</td>
                <td className="px-3 py-2 font-mono">
                  {fmt(a.success_rate)}
                </td>
                <td className="px-3 py-2 font-mono">{fmt(a.harm_rate)}</td>
                <td className="px-3 py-2 font-mono">
                  {fmt(a.composite_score)}
                </td>
                <td className="px-3 py-2 font-mono">
                  {fmt(a.cost_per_success_usd, 3)}
                </td>
                <td className="px-3 py-2">{a.is_control ? "yes" : ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
