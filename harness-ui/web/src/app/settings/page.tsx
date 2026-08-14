"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { LlmProviderPanel } from "@/components/LlmProviderPanel";
import { getLlmConfig } from "@/lib/api";
import type { LlmConfig, ProviderView } from "@/lib/types";

export default function SettingsPage() {
  const [config, setConfig] = useState<LlmConfig | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void getLlmConfig()
      .then(setConfig)
      .catch((e: Error) => setError(e.message));
  }, []);

  function onOpenai(next: ProviderView) {
    setConfig((c) => {
      if (!c) return c;
      return {
        ...c,
        providers: c.providers.map((p) => (p.id === next.id ? next : p)),
      };
    });
  }

  const openai = config?.providers.find((p) => p.id === "openai");
  const extra = (config?.providers ?? []).filter((p) => p.id !== "openai").length;

  return (
    <div className="max-w-2xl space-y-6">
      <header>
        <p className="section-label">Configuration</p>
        <h1 className="page-title">OpenAI</h1>
        <p className="page-lede">
          API key and endpoint for the OpenAI adapter. Extra OpenAI-compatible
          servers (vLLM, gateways, Azure) live on{" "}
          <Link href="/settings/providers/">Providers</Link>.
        </p>
      </header>

      {error && <p className="alert-error">{error}</p>}
      {config && (
        <p className="text-sm" style={{ color: "var(--muted)" }}>
          {config.adaptersNote}
        </p>
      )}

      {!openai && !error ? (
        <p className="text-sm" style={{ color: "var(--muted)" }}>
          Loading…
        </p>
      ) : openai ? (
        <LlmProviderPanel provider={openai} onChange={onOpenai} showAdapterNote />
      ) : null}

      <p className="text-sm" style={{ color: "var(--muted)" }}>
        {extra === 0 ? (
          <>
            No additional providers yet.{" "}
            <Link href="/settings/providers/">Add one</Link>.
          </>
        ) : (
          <>
            {extra} additional provider{extra === 1 ? "" : "s"}.{" "}
            <Link href="/settings/providers/">Manage</Link>.
          </>
        )}
      </p>
    </div>
  );
}
