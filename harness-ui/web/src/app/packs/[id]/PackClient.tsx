"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { DeleteButton } from "@/components/DeleteButton";
import { deletePack, readPack, validatePack, writePack } from "@/lib/api";
import { usePathId } from "@/lib/pathId";

export function PackClient({ id: bakedId }: { id: string }) {
  const router = useRouter();
  const id = usePathId("packs") || bakedId;
  const [yaml, setYaml] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [validMsg, setValidMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!id || id === "_") return;
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
        <p className="section-label">
          <Link href="/">Home</Link>
          {" / "}
          <Link href="/packs/">packs</Link>
          {" / "}
          <span className="font-mono">{id}</span>
        </p>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h1 className="page-title">Pack editor</h1>
          <DeleteButton
            label={id}
            disabled={busy}
            onDelete={async () => {
              await deletePack(id);
              router.push("/packs/");
            }}
          />
        </div>
        <p className="page-lede">
          Edit YAML, then validate. Invalid packs surface the adapter/Python
          error text — this UI does not re-parse the pack.
        </p>
      </header>

      <textarea
        value={yaml}
        onChange={(e) => setYaml(e.target.value)}
        spellCheck={false}
        rows={18}
        className="field-input min-h-[20rem]"
      />

      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          disabled={busy}
          onClick={() => void onValidate()}
          className="btn btn-primary"
        >
          Validate
        </button>
      </div>

      {error && (
        <pre className="alert-error overflow-x-auto whitespace-pre-wrap font-mono text-sm">
          {error}
        </pre>
      )}
      {validMsg && <p className="alert-note panel-signal">{validMsg}</p>}
    </div>
  );
}
