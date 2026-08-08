type Props = {
  refusalText: string;
  brokenBoundary?: string | null;
};

/** Exit-3 compare refusal — first-class explained panel, never a toast. */
export function RefusalPanel({ refusalText, brokenBoundary }: Props) {
  return (
    <section
      role="alert"
      className="mt-4 border-2 border-red-800 bg-red-50 p-4 text-red-950"
    >
      <h2 className="text-lg font-semibold tracking-tight">
        REFUSING TO POOL
      </h2>
      {brokenBoundary && (
        <p className="mt-1 text-sm">
          Broken boundary: <code className="font-mono">{brokenBoundary}</code>
        </p>
      )}
      <p className="mt-2 text-sm text-red-900">
        Compare will not merge these runs. Pooling across model, mcp_revision,
        skill condition, or report class is forbidden — the CLI exits 3 and
        the API returns this refusal verbatim.
      </p>
      <pre className="mt-3 overflow-x-auto whitespace-pre-wrap border border-red-300 bg-white p-3 font-mono text-xs text-zinc-900">
        {refusalText}
      </pre>
    </section>
  );
}
