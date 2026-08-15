"use client";

import { artifactUrl, isMockMode } from "@/lib/api";
import { useArtifactPath, usePathId } from "@/lib/pathId";

/**
 * Artifact viewer. iframe sandbox is intentionally `allow-scripts` only —
 * never add `allow-same-origin` (contracts.md / T3.5).
 */
export function ArtifactClient({
  runId: bakedRunId,
  name: bakedName,
}: {
  runId: string;
  name: string;
}) {
  const runId = usePathId("runs") || bakedRunId;
  const name = useArtifactPath() || bakedName;
  const src = isMockMode()
    ? mockArtifactSrc(runId, name)
    : artifactUrl(runId, name);

  return (
    <div className="space-y-3">
      <header>
        <p className="section-label">
          <a href={`/runs/${encodeURIComponent(runId)}/`}>Run {runId}</a>
          {" / "}
          <span className="font-mono">{name}</span>
        </p>
        <h1 className="page-title">Artifact viewer</h1>
        <p className="mt-1 font-mono text-xs" style={{ color: "var(--muted)" }}>
          sandbox=&quot;allow-scripts&quot; · no allow-same-origin
        </p>
      </header>

      <iframe
        title={`artifact ${name}`}
        src={src}
        sandbox="allow-scripts"
        className="h-[70vh] w-full border border-[var(--line)] bg-white"
      />
    </div>
  );
}

/** Inline mock document so the iframe has something to render without Java. */
function mockArtifactSrc(runId: string, name: string): string {
  const html = `<!DOCTYPE html><html><head><meta charset="utf-8"><title>${escapeHtml(name)}</title>
<style>body{font-family:system-ui,sans-serif;padding:1.5rem;color:#18181b;background:#fff}
code{font-family:ui-monospace,monospace}</style></head><body>
<h1>Mock artifact</h1>
<p>run=<code>${escapeHtml(runId)}</code> name=<code>${escapeHtml(name)}</code></p>
<p>This document is served as a blob URL for NEXT_PUBLIC_API_MOCK=1.</p>
<script>
try {
  var ping = window.parent && window.parent.location && window.parent.location.href;
  document.body.insertAdjacentHTML('beforeend', '<p id="parent">parent reachable: '+ping+'</p>');
} catch (e) {
  document.body.insertAdjacentHTML('beforeend', '<p id="parent">window.parent blocked (expected without allow-same-origin): '+e+'</p>');
}
</script>
</body></html>`;
  return `data:text/html;charset=utf-8,${encodeURIComponent(html)}`;
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
