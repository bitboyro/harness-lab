"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

/**
 * Static export only pre-renders a few ids (plus `_`). Deep links and SPA
 * fallback serve the `_` shell, so the real id must come from the pathname.
 */
export function usePathId(segment: string, param = "id"): string {
  const params = useParams();
  const baked = String(params?.[param] ?? "");
  const [id, setId] = useState(baked === "_" ? "" : baked);

  useEffect(() => {
    const parts = window.location.pathname.split("/").filter(Boolean);
    const i = parts.indexOf(segment);
    if (i >= 0 && parts[i + 1]) {
      setId(decodeURIComponent(parts[i + 1]));
      return;
    }
    if (baked && baked !== "_") setId(baked);
  }, [segment, baked]);

  return id || baked;
}

/** Full artifact path after `/artifacts/` (may contain slashes). */
export function useArtifactPath(): string {
  const params = useParams();
  const baked = String(params?.name ?? "");
  const [name, setName] = useState(baked === "_" ? "" : baked);

  useEffect(() => {
    const path = window.location.pathname.replace(/\/$/, "");
    const marker = "/artifacts/";
    const i = path.indexOf(marker);
    if (i >= 0) {
      const rest = path.slice(i + marker.length);
      if (rest && rest !== "_") {
        setName(decodeURIComponent(rest));
        return;
      }
    }
    if (baked && baked !== "_") setName(baked);
  }, [baked]);

  return name || baked;
}
