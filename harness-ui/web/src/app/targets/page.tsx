"use client";

import Link from "next/link";
import { useEffect, useState, type FormEvent } from "react";
import { DeleteButton } from "@/components/DeleteButton";
import { draftPack, deleteTarget, listTargets, uploadContract, uploadMcpUrl } from "@/lib/api";
import type { Target } from "@/lib/types";

export default function TargetsPage() {
  const [targets, setTargets] = useState<Target[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [mcpUrl, setMcpUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [lastPackId, setLastPackId] = useState<string | null>(null);

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
      setLastPackId(pack.id);
      setNote(`Drafted pack ${pack.id}.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <header>
        <p className="section-label">Surfaces</p>
        <h1 className="page-title">Targets</h1>
        <p className="page-lede">
          Upload an OpenAPI contract or register an MCP URL, then lint.
        </p>
      </header>

      {error && <p className="alert-error">{error}</p>}
      {note && lastPackId && (
        <p className="alert-note">
          {note}{" "}
          <Link href={`/packs/${encodeURIComponent(lastPackId)}/`} className="underline">
            Open pack editor
          </Link>
        </p>
      )}

      <div className="split-grid">
        <form onSubmit={onFile} className="panel space-y-3">
          <p className="section-label">OpenAPI</p>
          <h2 className="page-title" style={{ fontSize: "1.4rem" }}>
            Upload contract
          </h2>
          <input
            type="file"
            name="file"
            accept=".json,.yaml,.yml,application/json,text/yaml"
            className="block w-full text-sm"
          />
          <button type="submit" disabled={busy} className="btn btn-primary">
            Upload
          </button>
        </form>

        <form onSubmit={onMcp} className="panel space-y-3">
          <p className="section-label">MCP</p>
          <h2 className="page-title" style={{ fontSize: "1.4rem" }}>
            Register URL
          </h2>
          <input
            type="url"
            value={mcpUrl}
            onChange={(e) => setMcpUrl(e.target.value)}
            placeholder="http://127.0.0.1:8765/mcp"
            className="field-input"
          />
          <button type="submit" disabled={busy} className="btn btn-outline">
            Register
          </button>
        </form>
      </div>

      <section>
        <p className="section-label">Registered</p>
        <ul className="list-rows">
          {targets.map((t) => (
            <li key={t.id}>
              <div>
                <div className="font-mono text-sm">{t.id}</div>
                <div className="text-sm" style={{ color: "var(--muted)" }}>
                  {t.kind} · {t.label}
                </div>
              </div>
              <div className="flex flex-wrap items-center gap-4">
                <Link href={`/targets/${encodeURIComponent(t.id)}/`}>Open</Link>
                <Link href={`/targets/${encodeURIComponent(t.id)}/lint/`}>
                  Lint
                </Link>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => void onDraft(t.id)}
                  className="font-mono text-xs uppercase tracking-wider"
                  style={{ borderBottom: "1px solid var(--ink)" }}
                >
                  Draft pack
                </button>
                <DeleteButton
                  label={t.id}
                  disabled={busy}
                  onDelete={async () => {
                    await deleteTarget(t.id);
                    await refresh();
                  }}
                />
              </div>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
