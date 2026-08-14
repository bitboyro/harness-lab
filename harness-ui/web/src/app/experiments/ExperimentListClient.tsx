"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { DeleteButton } from "@/components/DeleteButton";
import { listExperiments, deleteExperiment } from "@/lib/api";
import type { ExperimentSummary } from "@/lib/types";

export function ExperimentListClient() {
  const router = useRouter();
  const [items, setItems] = useState<ExperimentSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);

  function refresh() {
    void listExperiments()
      .then(setItems)
      .catch((e: Error) => setError(e.message));
  }

  useEffect(() => {
    refresh();
  }, []);

  async function remove(id: string) {
    setDeleting(id);
    try {
      await deleteExperiment(id);
      refresh();
    } finally {
      setDeleting(null);
    }
  }

  if (error) return <p className="alert-error">{error}</p>;

  return (
    <div className="space-y-4">
      <div className="cta-row">
        <Link href="/experiments/new/from-openapi/" className="btn btn-primary">
          From OpenAPI
        </Link>
        <Link href="/experiments/new/" className="btn btn-outline">
          Plan template
        </Link>
      </div>
      {items.length === 0 ? (
        <p className="text-sm" style={{ color: "var(--muted)" }}>
          No experiments yet. Import a plan or copy an example sidecar.
        </p>
      ) : (
        <ul className="list-rows">
          {items.map((e) => (
            <li key={e.id}>
              <span>
                <span className="font-mono text-sm">{e.id}</span>
                <span className="ml-2 text-sm" style={{ color: "var(--muted)" }}>
                  {e.status}
                  {e.planId ? ` · plan ${e.planId}` : ""}
                  {e.coverageFraction != null
                    ? ` · ${Math.round(e.coverageFraction * 100)}%`
                    : ""}
                  {e.model ? ` · ${e.model}` : ""}
                </span>
              </span>
              <span className="flex flex-wrap items-center gap-3">
                <Link href={`/experiments/${encodeURIComponent(e.id)}/`}>Open</Link>
                <DeleteButton
                  label={e.id}
                  disabled={deleting === e.id}
                  onDelete={async () => {
                    await remove(e.id);
                    router.refresh();
                  }}
                />
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
