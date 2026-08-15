type Props = {
  refusalText: string;
  brokenBoundary?: string | null;
};

/** Exit-3 compare refusal — first-class explained panel, never a toast. */
export function RefusalPanel({ refusalText, brokenBoundary }: Props) {
  return (
    <section role="alert" className="panel mt-4" style={{ borderColor: "var(--rust)", background: "var(--danger-bg)" }}>
      <p className="section-label">Compare</p>
      <h2 className="page-title" style={{ fontSize: "1.75rem", color: "var(--danger)" }}>
        REFUSING TO POOL
      </h2>
      {brokenBoundary && (
        <p className="mt-1 text-sm">
          Broken boundary: <code className="font-mono">{brokenBoundary}</code>
        </p>
      )}
      <p className="mt-2 text-sm" style={{ color: "var(--ink-soft)" }}>
        Compare will not merge these runs. Pooling across model, mcp_revision,
        skill condition, or report class is forbidden — the CLI exits 3 and
        the API returns this refusal verbatim.
      </p>
      <pre className="mt-3 overflow-x-auto whitespace-pre-wrap border border-[var(--line)] bg-[rgba(255,255,255,0.65)] p-3 font-mono text-xs">
        {refusalText}
      </pre>
    </section>
  );
}
