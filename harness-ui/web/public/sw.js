/* Minimal PWA shell + last-viewed report cache (T3.6). */
const SHELL = "harness-ui-shell-v18";
const REPORTS = "harness-ui-reports-v1";

const SHELL_URLS = [
  "./",
  "./index.html",
  "./manifest.webmanifest",
  "./compare/",
  "./targets/",
  "./packs/",
  "./runs/new/",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(SHELL).then((cache) => cache.addAll(SHELL_URLS)).then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;

  const url = new URL(req.url);

  // Cache report JSON from the control API for offline open.
  if (url.pathname.match(/\/api\/v1\/runs\/[^/]+\/report\/?$/)) {
    event.respondWith(
      fetch(req)
        .then((res) => {
          if (res.ok) {
            const copy = res.clone();
            caches.open(REPORTS).then((c) => c.put(req, copy));
          }
          return res;
        })
        .catch(() => caches.match(req).then((hit) => hit || Response.error())),
    );
    return;
  }

  // App shell: network first, fall back to cache.
  if (url.origin === self.location.origin) {
    event.respondWith(
      fetch(req)
        .then((res) => {
          if (res.ok && req.mode === "navigate") {
            const copy = res.clone();
            caches.open(SHELL).then((c) => c.put(req, copy));
          }
          return res;
        })
        .catch(() =>
          caches.match(req).then((hit) => hit || caches.match("./index.html")),
        ),
    );
  }
});
