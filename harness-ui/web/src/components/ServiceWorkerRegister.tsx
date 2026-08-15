"use client";

import { useEffect } from "react";

/** Registers the shell/report cache SW (T3.6). */
export function ServiceWorkerRegister() {
  useEffect(() => {
    if (typeof window === "undefined" || !("serviceWorker" in navigator)) {
      return;
    }
    // Static export serves /sw.js from public/
    void navigator.serviceWorker.register("/sw.js").catch(() => {
      /* offline / file:// — ignore */
    });
  }, []);
  return null;
}
