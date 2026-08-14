"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { DeleteButton } from "@/components/DeleteButton";
import {
  deleteTarget,
  draftPack,
  getTarget,
  readTargetContract,
  writeTargetContract,
} from "@/lib/api";
import { usePathId } from "@/lib/pathId";
import type { Target, TargetContract } from "@/lib/types";

export function TargetClient({ id: bakedId }: { id: string }) {
  const router = useRouter();
  const id = usePathId("targets") || bakedId;
  const [target, setTarget] = useState<Target | null>(null);
  const [contract, setContract] = useState<TargetContract | null>(null);
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!id || id === "_") return;
    void Promise.all([getTarget(id), readTargetContract(id)])
      .then(([t, c]) => {
        setTarget(t);
        setContract(c);
        setText(c.text);
      })
      .catch((e: Error) => setError(e.message));
  }, [id]);

  async function onSave() {
    setBusy(true);
    setError(null);
    setNote(null);
    try {
      await writeTargetContract(id, text);
      setNote("Saved.");
      const t = await getTarget(id);
      setTarget(t);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function onDraftPack() {
    setBusy(true);
    setError(null);
    setNote(null);
    try {
      await writeTargetContract(id, text);
      const pack = await draftPack(id);
      setNote(`Drafted pack ${pack.id}.`);
      router.push(`/packs/${encodeURIComponent(pack.id)}/`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  if (!id || id === "_") {
    return (
      <p className="text-sm" style={{ color: "var(--muted)" }}>
        Missing target id.
      </p>
    );
  }

  const isOpenApi = target?.kind === "openapi";

  return (
    <div className="space-y-4">
      <header>
        <p className="section-label">
          <Link href="/">Home</Link>
          {" / "}
          <Link href="/targets/">targets</Link>
          {" / "}
          <span className="font-mono">{id}</span>
        </p>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="page-title font-mono">{id}</h1>
            {target && (
              <p className="page-lede">
                {target.kind} · {target.label}
              </p>
            )}
          </div>
          <DeleteButton
            label={id}
            disabled={busy}
            onDelete={async () => {
              await deleteTarget(id);
              router.push("/targets/");
            }}
          />
        </div>
      </header>

      {error && <p className="alert-error">{error}</p>}
      {note && !error && <p className="alert-note">{note}</p>}

      {contract?.format === "mcp-url" ? (
        <div className="panel space-y-3">
          <p className="section-label">MCP server</p>
          <input
            type="url"
            value={text}
            onChange={(e) => setText(e.target.value)}
            className="field-input"
            spellCheck={false}
          />
        </div>
      ) : (
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          spellCheck={false}
          rows={22}
          className="field-input min-h-[24rem] font-mono text-sm"
          aria-label="OpenAPI contract"
        />
      )}

      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          disabled={busy}
          onClick={() => void onSave()}
          className="btn btn-primary"
        >
          Save
        </button>
        {isOpenApi && (
          <Link
            href={`/targets/${encodeURIComponent(id)}/lint/`}
            className="btn btn-outline"
          >
            Lint
          </Link>
        )}
        <button
          type="button"
          disabled={busy}
          onClick={() => void onDraftPack()}
          className="btn btn-outline"
        >
          Draft pack
        </button>
      </div>
    </div>
  );
}
