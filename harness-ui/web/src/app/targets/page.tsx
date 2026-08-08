"use client";

import Link from "next/link";
import { useEffect, useState, type FormEvent } from "react";
import { draftPack, listTargets, uploadContract, uploadMcpUrl } from "@/lib/api";
import type { Target } from "@/lib/types";

export default function TargetsPage() {
  const [targets, setTargets] = useState<Target[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [mcpUrl, setMcpUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  async function refresh() {
    setTargets(await listTargets());
  }

  useEffect(() => {
    void refresh().catch((e: Error) => setError(e.message));
  }, []);

  async function onFile(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    const file = fd.get("file");
    if (!(file instanceof File) || !file.size) {
      setError("Choose an OpenAPI file.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await uploadContract(file);
      e.currentTarget.reset();
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function onMcp(e: FormEvent) {
    e.preventDefault();
    if (!mcpUrl.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await uploadMcpUrl(mcpUrl.trim());
      setMcpUrl("");
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function onDraft(targetId: string) {
    setBusy(true);
    setNote(null);
    setError(null);
    try {
      const pack = await draftPack(targetId);
      setNote(`Drafted pack ${pack.id} → /packs/${pack.id}/`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-xl font-semibold text-zinc-900">Targets</h1>
        <p className="mt-1 text-sm text-zinc-600">
          Upload an OpenAPI contract or register an MCP URL, then lint.
        </p>
      </header>

      {error && (
        <p className="border border-red-300 bg-red-50 p-3 text-sm text-red-900">
          {error}
        </p>
      )}
      {note && (
        <p className="border border-zinc-300 bg-white p-3 text-sm">
          {note}{" "}
          <Link href="/packs/demo/" className="underline">
            Open pack editor
          </Link>
        </p>
      )}

      <form
        onSubmit={onFile}
        className="space-y-3 border border-zinc-300 bg-white p-4"
      >
        <h2 className="text-sm font-semibold">Upload OpenAPI</h2>
        <input
          type="file"
          name="file"
          accept=".json,.yaml,.yml,application/json,text/yaml"
          className="block w-full text-sm"
        />
        <button
          type="submit"
          disabled={busy}
          className="border border-zinc-800 bg-zinc-900 px-3 py-1.5 text-sm text-white"
        >
          Upload
        </button>
      </form>

      <form
        onSubmit={onMcp}
        className="space-y-3 border border-zinc-300 bg-white p-4"
      >
        <h2 className="text-sm font-semibold">MCP URL</h2>
        <input
          type="url"
          value={mcpUrl}
          onChange={(e) => setMcpUrl(e.target.value)}
          placeholder="http://127.0.0.1:8765/mcp"
          className="w-full border border-zinc-300 px-2 py-1.5 font-mono text-sm"
        />
        <button
          type="submit"
          disabled={busy}
          className="border border-zinc-800 bg-zinc-900 px-3 py-1.5 text-sm text-white"
        >
          Register
        </button>
      </form>

      <section>
        <h2 className="mb-2 font-semibold text-zinc-900">Registered</h2>
        <ul className="divide-y divide-zinc-200 border border-zinc-300 bg-white">
          {targets.map((t) => (
            <li
              key={t.id}
              className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 text-sm"
            >
              <div>
                <div className="font-mono">{t.id}</div>
                <div className="text-zinc-500">
                  {t.kind} · {t.label}
                </div>
              </div>
              <div className="flex gap-3">
                <Link
                  href={`/targets/${encodeURIComponent(t.id)}/lint/`}
                  className="underline"
                >
                  Lint
                </Link>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => void onDraft(t.id)}
                  className="underline"
                >
                  Draft pack
                </button>
              </div>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
