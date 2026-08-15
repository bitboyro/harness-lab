"use client";

import { useCallback, useEffect, useState, type ReactNode } from "react";
import { ArmChip } from "@/components/ArmChip";
import { getTranscript, listCells } from "@/lib/api";
import type { CellRef } from "@/lib/types";

type Props = {
  runId: string;
};

function cellKey(c: CellRef): string {
  return `${c.arm}\0${c.taskId}\0${c.repeat}`;
}

const PAGE_SIZE = 10;

const COLLAPSED_LINE =
  /^\s*system\s+\[(task preamble|\d[\d,]* chars of packaging material)\]\s*$|^\s+… \d+ more lines\s*$/;

function hasCollapsedSections(text: string): boolean {
  return text.split("\n").some((line) => COLLAPSED_LINE.test(line.replace(/\u001b\[[0-9;]*m/g, "")));
}

export function TranscriptViewer({ runId }: Props) {
  const [cells, setCells] = useState<CellRef[]>([]);
  const [selected, setSelected] = useState<CellRef | null>(null);
  const [text, setText] = useState<string | null>(null);
  const [verbose, setVerbose] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(0);

  useEffect(() => {
    let cancelled = false;
    void listCells(runId)
      .then((rows) => {
        if (!cancelled) {
          setCells(rows);
          setPage(0);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setCells([]);
          setPage(0);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [runId]);

  const pageCount = Math.max(1, Math.ceil(cells.length / PAGE_SIZE));
  const safePage = Math.min(page, pageCount - 1);
  const pageStart = safePage * PAGE_SIZE;
  const pageCells = cells.slice(pageStart, pageStart + PAGE_SIZE);
  const rangeEnd = Math.min(pageStart + PAGE_SIZE, cells.length);

  const loadTranscript = useCallback(
    async (cell: CellRef, full: boolean) => {
      setLoading(true);
      setError(null);
      setText(null);
      try {
        const resp = await getTranscript(runId, cell.arm, cell.taskId, cell.repeat, full);
        setText(resp.text);
        setVerbose(full);
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setLoading(false);
      }
    },
    [runId],
  );

  const openCell = useCallback(
    async (cell: CellRef) => {
      setSelected(cell);
      setVerbose(false);
      await loadTranscript(cell, false);
    },
    [loadTranscript],
  );

  const toggleVerbose = useCallback(async () => {
    if (!selected) return;
    await loadTranscript(selected, !verbose);
  }, [loadTranscript, selected, verbose]);

  if (cells.length === 0) {
    return null;
  }

  const collapsed = text ? hasCollapsedSections(text) : false;

  return (
    <section className="space-y-4">
      <div>
        <p className="section-label">Transcripts</p>
        <p className="text-sm" style={{ color: "var(--muted)" }}>
          Showcase layout — same rendering as live{" "}
          <code className="text-xs">harness run --stream</code>. Collapsed preamble,
          packaging, and code blocks can be expanded below.
        </p>
      </div>

      <div className="panel overflow-x-auto !p-0">
        <table className="data-table">
          <thead>
            <tr>
              <th>Arm</th>
              <th>Task</th>
              <th>Rep</th>
              <th>Outcome</th>
              <th>Turns</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {pageCells.map((c) => {
              const active = selected && cellKey(selected) === cellKey(c);
              return (
                <tr key={cellKey(c)} style={active ? { background: "rgba(200,241,53,0.12)" } : undefined}>
                  <td>
                    <ArmChip arm={c.arm} />
                  </td>
                  <td className="font-mono text-xs">{c.taskId}</td>
                  <td className="font-mono">{c.repeat}</td>
                  <td className="font-mono">{c.outcome ?? "—"}</td>
                  <td className="font-mono">
                    {c.turns}
                    {c.calls > 0 ? ` · ${c.calls} calls` : ""}
                  </td>
                  <td>
                    <button
                      type="button"
                      className="btn btn-outline"
                      style={{ padding: "0.35rem 0.65rem", fontSize: "0.75rem" }}
                      onClick={() => void openCell(c)}
                    >
                      {active ? "Selected" : "View turns"}
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {cells.length > PAGE_SIZE && (
          <div className="table-pager">
            <p className="table-pager-meta">
              {pageStart + 1}–{rangeEnd} of {cells.length}
            </p>
            <div className="table-pager-actions">
              <button
                type="button"
                className="btn btn-ghost"
                style={{ padding: "0.3rem 0.65rem", fontSize: "0.72rem" }}
                disabled={safePage === 0}
                onClick={() => setPage((p) => Math.max(0, p - 1))}
              >
                Previous
              </button>
              <span className="table-pager-meta">
                Page {safePage + 1} / {pageCount}
              </span>
              <button
                type="button"
                className="btn btn-ghost"
                style={{ padding: "0.3rem 0.65rem", fontSize: "0.72rem" }}
                disabled={safePage >= pageCount - 1}
                onClick={() => setPage((p) => Math.min(pageCount - 1, p + 1))}
              >
                Next
              </button>
            </div>
          </div>
        )}
      </div>

      {(loading || error || text) && (
        <div className="panel space-y-3">
          {selected && (
            <div className="flex flex-wrap items-center justify-between gap-3">
              <p className="section-label !mb-0">
                <ArmChip arm={selected.arm} /> / {selected.taskId} / repeat{" "}
                {selected.repeat}
              </p>
              {text && (
                <div className="flex flex-wrap items-center gap-2">
                  {collapsed && !verbose && (
                    <span className="text-xs" style={{ color: "var(--muted)" }}>
                      Preamble, packaging, or code truncated
                    </span>
                  )}
                  <button
                    type="button"
                    className="btn btn-ghost"
                    style={{ padding: "0.3rem 0.65rem", fontSize: "0.72rem" }}
                    disabled={loading}
                    onClick={() => void toggleVerbose()}
                  >
                    {verbose ? "Collapse sections" : "Expand all sections"}
                  </button>
                </div>
              )}
            </div>
          )}
          {loading && (
            <p className="text-sm" style={{ color: "var(--muted)" }}>
              Loading transcript…
            </p>
          )}
          {error && <p className="alert-error">{error}</p>}
          {text && (
            <pre className="transcript-showcase">
              {highlightTranscript(text, { verbose, onExpand: () => void toggleVerbose() })}
            </pre>
          )}
        </div>
      )}
    </section>
  );
}

type HighlightOpts = {
  verbose: boolean;
  onExpand: () => void;
};

/** Light line-based emphasis for the showcase transcript format. */
function highlightTranscript(raw: string, opts: HighlightOpts): ReactNode[] {
  return raw.split("\n").map((line, i) => {
    const plain = line.replace(/\u001b\[[0-9;]*m/g, "");
    let className = "transcript-line";
    if (line.startsWith("┌─")) className += " transcript-head";
    else if (line.startsWith("── turn")) className += " transcript-turn";
    else if (line.includes("★ FINAL ANSWER")) className += " transcript-final";
    else if (line.startsWith("└─")) className += " transcript-foot";
    else if (/^\s+(system|user|assistant)\b/.test(line)) className += " transcript-role";
    else if (/^\s+→/.test(line) || /^\s+←/.test(line)) className += " transcript-call";

    const collapsed = !opts.verbose && COLLAPSED_LINE.test(plain);
    if (collapsed) {
      className += " transcript-collapsed";
      return (
        <button
          key={i}
          type="button"
          className={className}
          title="Expand preamble, packaging material, or code"
          onClick={opts.onExpand}
        >
          {line}
          {"\n"}
        </button>
      );
    }

    return (
      <span key={i} className={className}>
        {line}
        {"\n"}
      </span>
    );
  });
}
