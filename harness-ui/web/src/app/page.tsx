"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { listRuns, listTargets, readCachedReport } from "@/lib/api";
import type { RunSummary, Target } from "@/lib/types";

export default function HomePage() {
  const [targets, setTargets] = useState<Target[]>([]);
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [cached, setCached] = useState<ReturnType<typeof readCachedReport>>(null);

  useEffect(() => {
    setCached(readCachedReport());
    void Promise.all([listTargets(), listRuns()])
      .then(([t, r]) => {
        setTargets(t);
        setRuns(r);
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  return (
    <div className="space-y-8">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-900">
          harness-ui
        </h1>
        <p className="mt-1 max-w-2xl text-sm text-zinc-600">
          Control surface for targets, packs, runs, and compare. Judgment stays
          in the CLI / adapter — this UI only displays their JSON.
        </p>
      </header>

      {error && (
        <p className="border border-red-300 bg-red-50 p-3 text-sm text-red-900">
          {error}
        </p>
      )}

      <section>
        <div className="mb-2 flex items-baseline justify-between">
          <h2 className="font-semibold text-zinc-900">Targets</h2>
          <Link href="/targets/" className="text-sm underline">
            Manage
          </Link>
        </div>
        {targets.length === 0 ? (
          <p className="text-sm text-zinc-500">No targets yet.</p>
        ) : (
          <ul className="divide-y divide-zinc-200 border border-zinc-300 bg-white">
            {targets.map((t) => (
              <li
                key={t.id}
                className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 text-sm"
              >
                <span>
                  <span className="font-mono">{t.id}</span>
                  <span className="ml-2 text-zinc-500">
                    {t.kind} · {t.label}
                  </span>
                </span>
                <Link
                  href={`/targets/${encodeURIComponent(t.id)}/lint/`}
                  className="underline"
                >
                  Lint
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section>
        <div className="mb-2 flex items-baseline justify-between">
          <h2 className="font-semibold text-zinc-900">Runs</h2>
          <Link href="/runs/new/" className="text-sm underline">
            New run
          </Link>
        </div>
        {runs.length === 0 ? (
          <p className="text-sm text-zinc-500">No runs yet.</p>
        ) : (
          <ul className="divide-y divide-zinc-200 border border-zinc-300 bg-white">
            {runs.map((r) => (
              <li
                key={r.id}
                className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 text-sm"
              >
                <span>
                  <span className="font-mono">{r.id}</span>
                  <span className="ml-2 text-zinc-500">
                    {r.status}
                    {r.model ? ` · ${r.model}` : ""}
                  </span>
                </span>
                <Link
                  href={`/runs/${encodeURIComponent(r.id)}/`}
                  className="underline"
                >
                  Open
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="text-sm text-zinc-600">
        <Link href="/packs/demo/" className="underline">
          Pack editor (demo)
        </Link>
        {" · "}
        <Link href="/compare/" className="underline">
          Compare runs
        </Link>
        {cached && (
          <>
            {" · "}
            <Link
              href={`/runs/${encodeURIComponent(cached.runId)}/`}
              className="underline"
            >
              Last report (cached): {cached.runId}
            </Link>
          </>
        )}
      </section>
    </div>
  );
}
