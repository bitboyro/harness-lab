"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { DeleteButton } from "@/components/DeleteButton";
import { deleteRun, listRuns } from "@/lib/api";
import type { RunSummary } from "@/lib/types";

function fmtWhen(iso: string | null | undefined): string | null {
  if (!iso) return null;
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

export function RunsHubClient() {
  const [items, setItems] = useState<RunSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);

  const refresh = useCallback(() => {
    void listRuns()
      .then(setItems)
      .catch((e: Error) => setError(e.message));
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function removeRun(id: string) {
    setDeleting(id);
    try {
      await deleteRun(id);
      refresh();
    } finally {
      setDeleting(null);
    }
  }

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="section-label">Catalog</p>
          <h2 className="page-title" style={{ fontSize: "1.45rem" }}>
            All runs
          </h2>
        </div>
        <div className="cta-row !mt-0">
          <Link href="/compare/" className="btn btn-outline">
            Compare runs
          </Link>
          <Link href="/runs/new/" className="btn btn-primary">
            New run
          </Link>
        </div>
      </div>

      {error && <p className="alert-error">{error}</p>}

      {items.length === 0 ? (
        <p className="text-sm" style={{ color: "var(--muted)" }}>
          No runs on disk yet —{" "}
          <Link href="/runs/new/" className="underline">
            start one
          </Link>{" "}
          or launch from an experiment.
        </p>
      ) : (
        <ul className="list-rows">
          {items.map((r) => {
            const when = fmtWhen(r.finishedAt ?? r.startedAt);
            return (
              <li key={r.id}>
                <span>
                  <span className="font-mono text-sm">{r.id}</span>
                  <span className="ml-2 text-sm" style={{ color: "var(--muted)" }}>
                    {r.status}
                    {when ? ` · ${when}` : ""}
                    {r.ledgerRows != null ? ` · ${r.ledgerRows} rows` : ""}
                  </span>
                </span>
                <span className="flex flex-wrap items-center gap-3">
                  <Link href={`/runs/${encodeURIComponent(r.id)}/`}>Open</Link>
                  <DeleteButton
                    label={r.id}
                    disabled={deleting === r.id}
                    onDelete={() => removeRun(r.id)}
                  />
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
