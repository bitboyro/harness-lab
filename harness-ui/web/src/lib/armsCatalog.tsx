"use client";

import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { getRunDefaults } from "@/lib/api";
import type { PresetOption } from "@/lib/types";

type ArmsCatalog = {
  byId: Map<string, PresetOption>;
  presets: PresetOption[];
  ready: boolean;
};

const ArmsCatalogContext = createContext<ArmsCatalog>({
  byId: new Map(),
  presets: [],
  ready: false,
});

export function ArmsCatalogProvider({ children }: { children: React.ReactNode }) {
  const [presets, setPresets] = useState<PresetOption[]>([]);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    void getRunDefaults()
      .then((cfg) => {
        setPresets(cfg.presets ?? []);
        setReady(true);
      })
      .catch(() => setReady(true));
  }, []);

  const value = useMemo<ArmsCatalog>(() => {
    const byId = new Map(presets.map((p) => [p.id, p]));
    return { byId, presets, ready };
  }, [presets, ready]);

  return (
    <ArmsCatalogContext.Provider value={value}>
      {children}
    </ArmsCatalogContext.Provider>
  );
}

export function useArmsCatalog(): ArmsCatalog {
  return useContext(ArmsCatalogContext);
}

/** Resolve a short label + tooltip text for an arm id. */
export function useArmInfo(
  armId: string,
  overrides?: { label?: string | null; description?: string | null },
): { label: string; description: string } {
  const { byId } = useArmsCatalog();
  const catalog = byId.get(armId);
  const label = overrides?.label || catalog?.label || armId;
  const description =
    overrides?.description ||
    catalog?.description ||
    catalog?.label ||
    armId;
  return { label, description };
}
