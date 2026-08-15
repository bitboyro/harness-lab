"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { DeleteButton } from "@/components/DeleteButton";
import { deletePack, listPacks } from "@/lib/api";
import type { PackRef } from "@/lib/types";

export function PacksListClient() {
  const router = useRouter();
  const [items, setItems] = useState<PackRef[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);

  const refresh = useCallback(() => {
    void listPacks()
      .then(setItems)
      .catch((e: Error) => setError(e.message));
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function remove(id: string) {
    setDeleting(id);
    try {
      await deletePack(id);
      refresh();
    } finally {
      setDeleting(null);
    }
  }

  return (
    <section className="space-y-4">
      {error && <p className="alert-error">{error}</p>}

      {items.length === 0 ? (
        <p className="text-sm" style={{ color: "var(--muted)" }}>
          No packs yet — draft one from a{" "}
          <Link href="/targets/" className="underline">
            target
          </Link>
          .
        </p>
      ) : (
        <ul className="list-rows">
          {items.map((p) => (
            <li key={p.id}>
              <span>
                <span className="font-mono text-sm">{p.id}</span>
                <span className="ml-2 text-sm" style={{ color: "var(--muted)" }}>
                  {p.valid ? "valid" : "invalid"}
                  {p.error ? ` · ${p.error}` : ""}
                </span>
              </span>
              <span className="flex flex-wrap items-center gap-3">
                <Link href={`/packs/${encodeURIComponent(p.id)}/`}>Edit</Link>
                <DeleteButton
                  label={p.id}
                  disabled={deleting === p.id}
                  onDelete={async () => {
                    await remove(p.id);
                    router.refresh();
                  }}
                />
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
