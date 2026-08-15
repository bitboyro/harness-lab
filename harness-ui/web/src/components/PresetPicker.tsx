"use client";

import type { PresetOption } from "@/lib/types";

type Props = {
  presets: PresetOption[];
  selected: string[];
  bundles?: Record<string, string[]>;
  onChange: (next: string[]) => void;
  disabled?: boolean;
};

const GROUP_ORDER = ["Z", "A", "B", "C", "D", "E", "M"];

export function PresetPicker({
  presets,
  selected,
  bundles,
  onChange,
  disabled,
}: Props) {
  const set = new Set(selected);

  function toggle(id: string) {
    const next = new Set(set);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    onChange([...next].sort());
  }

  function applyBundle(ids: string[]) {
    onChange([...new Set(ids)].sort());
  }

  const byGroup = GROUP_ORDER.map((g) => ({
    group: g,
    items: presets.filter((p) => p.group === g),
  })).filter((g) => g.items.length > 0);

  return (
    <div className="space-y-3">
      {bundles && Object.keys(bundles).length > 0 && (
        <div className="flex flex-wrap gap-2">
          {Object.entries(bundles).map(([key, ids]) => (
            <button
              key={key}
              type="button"
              disabled={disabled}
              className="btn btn-ghost"
              style={{ padding: "0.25rem 0.55rem", fontSize: "0.75rem" }}
              onClick={() => applyBundle(ids)}
            >
              {key}
            </button>
          ))}
        </div>
      )}
      {byGroup.map(({ group, items }) => (
        <div key={group}>
          <p className="mb-1 font-mono text-xs uppercase tracking-wider" style={{ color: "var(--muted)" }}>
            {group}
          </p>
          <div className="flex flex-wrap gap-2">
            {items.map((p) => {
              const on = set.has(p.id);
              return (
                <button
                  key={p.id}
                  type="button"
                  disabled={disabled}
                  title={p.description ? `${p.label} — ${p.description}` : p.label}
                  className={`preset-chip${on ? " is-on" : ""}`}
                  onClick={() => toggle(p.id)}
                >
                  {p.id}
                </button>
              );
            })}
          </div>
        </div>
      ))}
      {selected.length > 0 && (
        <p className="font-mono text-xs" style={{ color: "var(--muted)" }}>
          {selected.join(", ")}
          {selected.some((id) => presets.find((p) => p.id === id)?.requiresSandbox)
            ? " · includes D arms (sandbox)"
            : ""}
        </p>
      )}
    </div>
  );
}
