"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { SearchSelect } from "@/components/SearchSelect";
import { listExperiments, listRuns, listTargets } from "@/lib/api";

type JumpOption = {
  id: string;
  label?: string;
  hint?: string;
  href: string;
};

/** Top-bar jump: search runs / experiments / targets instead of typing URLs. */
export function ResourceJump() {
  const router = useRouter();
  const [options, setOptions] = useState<JumpOption[]>([]);
  const [value, setValue] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void Promise.all([listRuns(), listExperiments(), listTargets()])
      .then(([runs, experiments, targets]) => {
        if (cancelled) return;
        const rows: JumpOption[] = [
          ...runs.map((r) => ({
            id: `run:${r.id}`,
            label: r.id,
            hint: `run · ${r.status}${r.model ? ` · ${r.model}` : ""}`,
            href: `/runs/${encodeURIComponent(r.id)}/`,
          })),
          ...experiments.map((e) => ({
            id: `exp:${e.id}`,
            label: e.id,
            hint: `experiment · ${e.status}${e.planId ? ` · plan ${e.planId}` : ""}`,
            href: `/experiments/${encodeURIComponent(e.id)}/`,
          })),
          ...targets.map((t) => ({
            id: `tgt:${t.id}`,
            label: t.label || t.id,
            hint: `target · ${t.kind} · ${t.id}`,
            href: `/targets/${encodeURIComponent(t.id)}/`,
          })),
        ];
        setOptions(rows);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  const selectOptions = useMemo(
    () =>
      options.map((o) => ({
        id: o.id,
        label: o.label,
        hint: o.hint,
      })),
    [options],
  );

  return (
    <div className="resource-jump">
      <SearchSelect
        options={selectOptions}
        value={value}
        onChange={(id) => {
          setValue(null);
          const hit = options.find((o) => o.id === id);
          if (hit) router.push(hit.href);
        }}
        placeholder="Search runs, experiments, targets…"
        emptyLabel=""
        allowClear
        className="resource-jump-select"
      />
    </div>
  );
}
