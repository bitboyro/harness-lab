import { ArmChip } from "@/components/ArmChip";
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
      <div className="panel panel-ink">
        <p className="section-label">Verdict</p>
        <h2 className="page-title" style={{ color: "var(--fog)", fontSize: "1.75rem" }}>
          Winner{" "}
          <span style={{ color: "var(--signal)" }}>
            {report.verdict.winner ? (
              <ArmChip
                arm={report.verdict.winner}
                label={report.arms[report.verdict.winner]?.name}
                description={report.arms[report.verdict.winner]?.description}
              />
            ) : (
              "none"
            )}
          </span>
        </h2>
        {report.verdict.reason && (
          <p className="mt-2 text-sm" style={{ color: "rgba(232,239,233,0.75)" }}>
            {report.verdict.reason}
          </p>
        )}
        {report.verdict.caveats.length > 0 && (
          <ul className="mt-3 space-y-1 text-sm" style={{ color: "rgba(232,239,233,0.7)" }}>
            {report.verdict.caveats.map((c) => (
              <li key={c}>· {c}</li>
            ))}
          </ul>
        )}
        <p className="mt-4 font-mono text-xs uppercase tracking-wider" style={{ color: "rgba(232,239,233,0.45)" }}>
          validation={report.validation} · model={report.run.model} · class=
          {report.run.report_class}
        </p>
      </div>

      <div className="panel overflow-x-auto !p-0">
        <table className="data-table">
          <thead>
            <tr>
              <th>Arm</th>
              <th>n</th>
              <th>Success</th>
              <th>Harm</th>
              <th>Score</th>
              <th>$/success</th>
              <th>Control</th>
            </tr>
          </thead>
          <tbody>
            {arms.map((a) => (
              <tr key={a.arm}>
                <td>
                  <ArmChip
                    arm={a.arm}
                    label={a.name ?? a.label}
                    description={a.description}
                  />
                  {a.name ? (
                    <span className="ml-2 text-sm" style={{ color: "var(--muted)" }}>
                      {a.name}
                    </span>
                  ) : null}
                </td>
                <td className="font-mono">{a.n}</td>
                <td className="font-mono">{fmt(a.success_rate)}</td>
                <td className="font-mono">{fmt(a.harm_rate)}</td>
                <td className="font-mono">{fmt(a.composite_score)}</td>
                <td className="font-mono">{fmt(a.cost_per_success_usd, 3)}</td>
                <td>{a.is_control ? "yes" : ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
