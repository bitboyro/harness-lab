"use client";

import { ArmChip } from "@/components/ArmChip";
import type { AdapterAnalysis, AnalysisSection } from "@/lib/types";

type Props = {
  analysis: AdapterAnalysis;
};

function formatCell(v: unknown): string {
  if (v == null) return "—";
  if (typeof v === "number") {
    if (Number.isNaN(v)) return "—";
    if (Math.abs(v) >= 1000) return v.toFixed(1);
    if (Math.abs(v) < 0.01 && v !== 0) return v.toExponential(2);
    return Number.isInteger(v) ? String(v) : v.toFixed(4).replace(/\.?0+$/, "");
  }
  if (typeof v === "boolean") return v ? "yes" : "no";
  return String(v);
}

function isArmHeader(h: string): boolean {
  const n = h.toLowerCase();
  return n === "arm" || n === "arms" || n === "preset" || n === "winner";
}

function looksLikeArmId(v: unknown): v is string {
  return typeof v === "string" && /^[A-Z][0-9A-Za-z-]*$/.test(v);
}

function SectionTable({
  sectionKey,
  section,
}: {
  sectionKey: string;
  section: AnalysisSection;
}) {
  return (
    <details
      className="panel !p-0"
      open={sectionKey === "standings" || sectionKey === "identity"}
    >
      <summary
        className="cursor-pointer select-none px-4 py-3 text-sm font-medium"
        style={{ color: "var(--ink)" }}
      >
        {section.title}
        <span
          className="ml-2 font-mono text-xs"
          style={{ color: "var(--muted)" }}
        >
          {sectionKey}
        </span>
      </summary>
      <div
        className="overflow-x-auto border-t px-0 pb-2"
        style={{ borderColor: "var(--line)" }}
      >
        {section.note ? (
          <p className="px-4 pt-2 text-xs" style={{ color: "var(--muted)" }}>
            {section.note}
          </p>
        ) : null}
        <table className="data-table">
          <thead>
            <tr>
              {section.headers.map((h) => (
                <th key={h}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {section.rows.map((row, i) => (
              <tr key={i}>
                {section.headers.map((h) => {
                  const v = row[h];
                  if (isArmHeader(h) && looksLikeArmId(v)) {
                    return (
                      <td key={h}>
                        <ArmChip arm={v} />
                      </td>
                    );
                  }
                  return (
                    <td key={h} className="font-mono text-xs">
                      {formatCell(v)}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}

export function AnalysisPanels({ analysis }: Props) {
  const keys = Object.keys(analysis.sections);
  if (keys.length === 0) {
    return (
      <p className="text-sm" style={{ color: "var(--muted)" }}>
        No analysis sections.
      </p>
    );
  }
  return (
    <section className="space-y-3">
      <div>
        <p className="section-label">Deep analysis</p>
        <p className="text-sm" style={{ color: "var(--muted)" }}>
          Same standings as the report, plus stability, tokens, cores, and
          audits. Free — reads the ledger only. Hover arm codes for packaging
          descriptions.
        </p>
      </div>
      {keys.map((key) => (
        <SectionTable
          key={key}
          sectionKey={key}
          section={analysis.sections[key]}
        />
      ))}
    </section>
  );
}
