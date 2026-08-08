"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { readPack, validatePack, writePack } from "@/lib/api";

export function PackClient({ id }: { id: string }) {
  const [yaml, setYaml] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [validMsg, setValidMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    void readPack(id)
      .then((p) => setYaml(p.yaml))
      .catch((e: Error) => setError(e.message));
  }, [id]);

  async function onValidate() {
    setBusy(true);
    setError(null);
    setValidMsg(null);
    try {
      const written = await writePack(id, yaml);
      if (!written.valid) {
        setError(written.error ?? "Invalid pack");
        return;
      }
      const result = await validatePack(id);
      if (!result.valid) {
        setError(result.error ?? "Validation failed");
        return;
      }
      setValidMsg(
        `Valid · pack_id=${result.pack_id ?? id}` +
          (result.task_count != null ? ` · tasks=${result.task_count}` : ""),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <header>
        <p className="text-sm text-zinc-500">
          <Link href="/" className="underline">
            Home
          </Link>
          {" / packs / "}
          <span className="font-mono">{id}</span>
        </p>
        <h1 className="mt-1 text-xl font-semibold text-zinc-900">
          Pack editor
        </h1>
        <p className="mt-1 text-sm text-zinc-600">
          Edit YAML, then validate. Invalid packs surface the adapter/Python
          error text — this UI does not re-parse the pack.
        </p>
      </header>

      <textarea
        value={yaml}
        onChange={(e) => setYaml(e.target.value)}
        spellCheck={false}
        rows={18}
        className="w-full border border-zinc-300 bg-white p-3 font-mono text-sm"
      />

      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          disabled={busy}
          onClick={() => void onValidate()}
          className="border border-zinc-800 bg-zinc-900 px-3 py-1.5 text-sm text-white"
        >
          Validate
        </button>
        <span className="text-xs text-zinc-500">
          Tip (mock): insert <code className="font-mono">INVALID</code> to force
          a PackError.
        </span>
      </div>

      {error && (
        <pre className="overflow-x-auto whitespace-pre-wrap border-2 border-red-800 bg-red-50 p-3 font-mono text-sm text-red-950">
          {error}
        </pre>
      )}
      {validMsg && (
        <p className="border border-emerald-700 bg-emerald-50 p-3 text-sm text-emerald-950">
          {validMsg}
        </p>
      )}
    </div>
  );
}
