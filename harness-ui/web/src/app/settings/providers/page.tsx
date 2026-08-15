"use client";

import Link from "next/link";
import { useEffect, useState, type FormEvent } from "react";
import { DeleteButton } from "@/components/DeleteButton";
import { LlmProviderPanel } from "@/components/LlmProviderPanel";
import { deleteProvider, getLlmConfig, upsertProvider } from "@/lib/api";
import type { LlmConfig, ProviderView } from "@/lib/types";

export default function ProvidersPage() {
  const [config, setConfig] = useState<LlmConfig | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [openId, setOpenId] = useState<string | null>(null);

  const [newId, setNewId] = useState("");
  const [newLabel, setNewLabel] = useState("");
  const [newUrl, setNewUrl] = useState("");
  const [newKey, setNewKey] = useState("");

  useEffect(() => {
    void getLlmConfig()
      .then(setConfig)
      .catch((e: Error) => setError(e.message));
  }, []);

  const extras = (config?.providers ?? []).filter((p) => !p.builtin);

  function replace(next: ProviderView) {
    setConfig((c) => {
      if (!c) return c;
      const exists = c.providers.some((p) => p.id === next.id);
      return {
        ...c,
        providers: exists
          ? c.providers.map((p) => (p.id === next.id ? next : p))
          : [...c.providers, next],
      };
    });
  }

  async function onAdd(e: FormEvent) {
    e.preventDefault();
    if (!newId.trim() || !newUrl.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const created = await upsertProvider(newId.trim().toLowerCase(), {
        label: newLabel.trim() || newId.trim(),
        adapter: "openai",
        baseUrl: newUrl.trim(),
        apiKey: newKey.trim() || undefined,
        models: [],
      });
      replace(created);
      setOpenId(created.id);
      setNewId("");
      setNewLabel("");
      setNewUrl("");
      setNewKey("");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="max-w-2xl space-y-6">
      <header>
        <p className="section-label">
          <Link href="/settings/">Settings</Link>
          {" / providers"}
        </p>
        <h1 className="page-title">Providers</h1>
        <p className="page-lede">
          The engine only ships an OpenAI adapter. Additional providers are
          named OpenAI-compatible endpoints — each with its own key, URL, and
          registered models.
        </p>
      </header>

      {error && <p className="alert-error">{error}</p>}

      <form onSubmit={onAdd} className="panel space-y-3">
        <p className="section-label">Add</p>
        <h2 className="page-title" style={{ fontSize: "1.4rem" }}>
          OpenAI-compatible endpoint
        </h2>
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="field-label">
            Id
            <input
              className="field-input"
              value={newId}
              onChange={(e) => setNewId(e.target.value)}
              placeholder="local-vllm"
              required
            />
          </label>
          <label className="field-label">
            Label
            <input
              className="field-input"
              value={newLabel}
              onChange={(e) => setNewLabel(e.target.value)}
              placeholder="Local vLLM"
            />
          </label>
          <label className="field-label sm:col-span-2">
            Base URL
            <input
              className="field-input"
              type="url"
              value={newUrl}
              onChange={(e) => setNewUrl(e.target.value)}
              placeholder="http://127.0.0.1:8000/v1"
              required
            />
          </label>
          <label className="field-label sm:col-span-2">
            API key
            <input
              className="field-input"
              type="password"
              autoComplete="off"
              value={newKey}
              onChange={(e) => setNewKey(e.target.value)}
              placeholder="optional if the server does not require one"
            />
          </label>
        </div>
        <button type="submit" disabled={busy} className="btn btn-primary">
          Add provider
        </button>
      </form>

      <section>
        <p className="section-label">Registered</p>
        {extras.length === 0 ? (
          <p className="text-sm" style={{ color: "var(--muted)" }}>
            None yet. OpenAI itself is configured on{" "}
            <Link href="/settings/">Settings</Link>.
          </p>
        ) : (
          <ul className="space-y-4">
            {extras.map((p) => (
              <li key={p.id} className="panel space-y-3">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <div className="font-mono text-sm">{p.id}</div>
                    <div className="text-sm" style={{ color: "var(--muted)" }}>
                      {p.label} · {p.baseUrl || "no URL"} ·{" "}
                      {p.models.length} model{p.models.length === 1 ? "" : "s"}
                    </div>
                  </div>
                  <div className="flex flex-wrap items-center gap-3">
                    <button
                      type="button"
                      className="font-mono text-xs uppercase tracking-wider"
                      style={{ borderBottom: "1px solid var(--ink)" }}
                      onClick={() => setOpenId(openId === p.id ? null : p.id)}
                    >
                      {openId === p.id ? "Close" : "Edit"}
                    </button>
                    <DeleteButton
                      label={p.id}
                      disabled={busy}
                      onDelete={async () => {
                        await deleteProvider(p.id);
                        setConfig((c) =>
                          c
                            ? {
                                ...c,
                                providers: c.providers.filter((x) => x.id !== p.id),
                              }
                            : c,
                        );
                      }}
                    />
                  </div>
                </div>
                {openId === p.id && (
                  <LlmProviderPanel provider={p} onChange={replace} />
                )}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
