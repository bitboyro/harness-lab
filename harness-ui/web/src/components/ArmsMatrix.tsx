"use client";

import { useArmsCatalog } from "@/lib/armsCatalog";
import { ArmChip } from "@/components/ArmChip";

const GROUP_ORDER = ["Z", "A", "B", "C", "D", "E", "M"];

type Props = {
  /** Highlight these arm ids (e.g. probe arms on a generate job). */
  highlight?: string[];
  compact?: boolean;
};

/** Full packaging-arm matrix with short label + description. */
export function ArmsMatrix({ highlight, compact }: Props) {
  const { presets, ready } = useArmsCatalog();
  const hi = new Set(highlight ?? []);

  if (!ready) {
    return (
      <p className="text-sm" style={{ color: "var(--muted)" }}>
        Loading arm catalog…
      </p>
    );
  }

  const byGroup = GROUP_ORDER.map((g) => ({
    group: g,
    items: presets.filter((p) => p.group === g),
  })).filter((g) => g.items.length > 0);

  return (
    <section className="space-y-3">
      <div>
        <p className="section-label">Packaging arms</p>
        {!compact && (
          <p className="text-sm" style={{ color: "var(--muted)" }}>
            An arm is one way of handing the API to the agent — all MCP tools,
            docs and curl, a skill, no tools, and so on. A run compares the
            same tasks across the arms you pick.
          </p>
        )}
      </div>
      <div className="panel overflow-x-auto !p-0">
        <table className="data-table">
          <thead>
            <tr>
              <th>Arm</th>
              <th>Short name</th>
              <th>Description</th>
            </tr>
          </thead>
          <tbody>
            {byGroup.flatMap(({ group, items }) =>
              items.map((p, i) => (
                <tr
                  key={p.id}
                  style={
                    hi.has(p.id)
                      ? { background: "var(--signal-soft)" }
                      : undefined
                  }
                >
                  <td>
                    {i === 0 ? (
                      <span
                        className="mr-2 font-mono text-xs uppercase"
                        style={{ color: "var(--muted)" }}
                      >
                        {group}
                      </span>
                    ) : null}
                    <ArmChip
                      arm={p.id}
                      label={p.label}
                      description={p.description}
                    />
                  </td>
                  <td className="text-sm">{p.label}</td>
                  <td className="text-sm" style={{ color: "var(--muted)" }}>
                    {p.description ?? "—"}
                  </td>
                </tr>
              )),
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
