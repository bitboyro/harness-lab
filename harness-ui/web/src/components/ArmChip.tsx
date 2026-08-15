"use client";

import { useArmInfo } from "@/lib/armsCatalog";

type Props = {
  arm: string;
  /** Prefer report/adapter short name when present. */
  label?: string | null;
  /** Prefer report/adapter long description when present. */
  description?: string | null;
  className?: string;
};

/** Mono arm id with native + CSS tooltip describing the packaging method. */
export function ArmChip({ arm, label, description, className = "" }: Props) {
  const info = useArmInfo(arm, { label, description });
  const tip = `${info.label} — ${info.description}`;

  return (
    <span
      className={`arm-chip ${className}`.trim()}
      title={tip}
      data-tooltip={tip}
      tabIndex={0}
      aria-label={tip}
    >
      <span className="font-mono">{arm}</span>
    </span>
  );
}
