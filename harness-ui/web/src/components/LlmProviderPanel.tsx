"use client";

import { useEffect, useState, type FormEvent } from "react";
import { deleteModel, upsertModel, upsertProvider } from "@/lib/api";
import type { ProviderView, RegisteredModel } from "@/lib/types";

type Props = {
  provider: ProviderView;
  onChange: (next: ProviderView) => void;
  showAdapterNote?: boolean;
};

export function LlmProviderPanel({ provider, onChange, showAdapterNote }: Props) {
  const [label, setLabel] = useState(provider.label);
  const [baseUrl, setBaseUrl] = useState(provider.baseUrl ?? "");
  const [apiKey, setApiKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  const [modelId, setModelId] = useState("");
  const [modelLabel, setModelLabel] = useState("");
  const [modelPrice, setModelPrice] = useState("");

  useEffect(() => {
    setLabel(provider.label);
    setBaseUrl(provider.baseUrl ?? "");
  }, [provider.id, provider.label, provider.baseUrl]);

  async function onSave(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setNote(null);
    try {
      const next = await upsertProvider(provider.id, {
        label,
        adapter: "openai",
        baseUrl,
        apiKey: apiKey.trim() ? apiKey.trim() : undefined,
      });
      setApiKey("");
      onChange(next);
      setNote("Saved.");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function onClearKey() {
    setBusy(true);
    setError(null);
    try {
      const next = await upsertProvider(provider.id, {
        label,
        adapter: "openai",
        baseUrl,
        apiKey: "",
      });
      setApiKey("");
      onChange(next);
      setNote("API key cleared.");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function onAddModel(e: FormEvent) {
    e.preventDefault();
    if (!modelId.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const next = await upsertModel(provider.id, modelId.trim(), {
        label: modelLabel.trim() || null,
        price: modelPrice.trim() || null,
      });
      setModelId("");
      setModelLabel("");
      setModelPrice("");
      onChange(next);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function onRemoveModel(id: string) {
    setBusy(true);
    setError(null);
    try {
      onChange(await deleteModel(provider.id, id));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  const keyStatus = provider.apiKeySet
    ? `Stored key ${provider.apiKeyHint ?? "set"}`
    : provider.processEnvKeySet
      ? "Using OPENAI_API_KEY from the server environment"
      : "No key configured";

  return (
    <div className="space-y-5">
      {error && <p className="alert-error">{error}</p>}
      {note && <p className="alert-note">{note}</p>}

      <form onSubmit={onSave} className="panel space-y-4">
        <p className="section-label">Credentials</p>
        {showAdapterNote && (
          <p className="text-sm" style={{ color: "var(--muted)" }}>
            Uses the OpenAI adapter. Point the URL at api.openai.com, a gateway,
            Azure OpenAI, vLLM, or any compatible server.
          </p>
        )}
        {!provider.builtin && (
          <label className="field-label">
            Label
            <input
              className="field-input"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
            />
          </label>
        )}
        <label className="field-label">
          API key
          <input
            className="field-input"
            type="password"
            autoComplete="off"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder={
              provider.apiKeySet ? "Leave blank to keep the stored key" : "sk-…"
            }
          />
        </label>
        <p className="text-xs" style={{ color: "var(--muted)" }}>
          {keyStatus}. Keys saved here go to{" "}
          <code>secrets/providers.env</code>. The harness CLI also loads{" "}
          <code>.env</code> from the repo.
        </p>
        <label className="field-label">
          Base URL
          <input
            className="field-input"
            type="url"
            value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
            placeholder={
              provider.builtin
                ? "https://api.openai.com/v1 (default)"
                : "http://127.0.0.1:8000/v1"
            }
          />
        </label>
        {provider.processBaseUrl && !baseUrl && (
          <p className="text-xs" style={{ color: "var(--muted)" }}>
            Server env <code>OPENAI_BASE_URL</code>={provider.processBaseUrl}
          </p>
        )}
        <div className="flex flex-wrap gap-2">
          <button type="submit" disabled={busy} className="btn btn-primary">
            Save
          </button>
          {provider.apiKeySet && (
            <button
              type="button"
              disabled={busy}
              className="btn btn-ghost"
              onClick={() => void onClearKey()}
            >
              Clear key
            </button>
          )}
        </div>
      </form>

      <section className="panel space-y-4">
        <p className="section-label">Registered models</p>
        <p className="text-sm" style={{ color: "var(--muted)" }}>
          Run and experiment pickers use this list. Models not in the harness
          catalogue need a price card so cost projection can refuse to guess.
        </p>
        {provider.models.length === 0 ? (
          <p className="text-sm" style={{ color: "var(--muted)" }}>
            None yet — the built-in catalogue ({" "}
            <code>gpt-5.6-luna</code>) stays available until you register one.
          </p>
        ) : (
          <ul className="list-rows">
            {provider.models.map((m: RegisteredModel) => (
              <li key={m.id}>
                <div>
                  <div className="font-mono text-sm">{m.id}</div>
                  <div className="text-sm" style={{ color: "var(--muted)" }}>
                    {m.label && m.label !== m.id ? `${m.label} · ` : ""}
                    {m.price ? `price ${m.price}` : "catalogue price, if known"}
                  </div>
                </div>
                <button
                  type="button"
                  disabled={busy}
                  className="font-mono text-xs uppercase tracking-wider"
                  style={{ borderBottom: "1px solid var(--ink)" }}
                  onClick={() => void onRemoveModel(m.id)}
                >
                  Remove
                </button>
              </li>
            ))}
          </ul>
        )}
        <form onSubmit={onAddModel} className="grid gap-3 sm:grid-cols-2">
          <label className="field-label">
            Model id
            <input
              className="field-input"
              value={modelId}
              onChange={(e) => setModelId(e.target.value)}
              placeholder="gpt-5.6-luna"
              required
            />
          </label>
          <label className="field-label">
            Label
            <input
              className="field-input"
              value={modelLabel}
              onChange={(e) => setModelLabel(e.target.value)}
              placeholder="optional"
            />
          </label>
          <label className="field-label sm:col-span-2">
            Price (USD / MTok)
            <input
              className="field-input"
              value={modelPrice}
              onChange={(e) => setModelPrice(e.target.value)}
              placeholder="in,out  or  in,cached,write,out"
            />
          </label>
          <div>
            <button type="submit" disabled={busy} className="btn btn-outline">
              Register model
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}
