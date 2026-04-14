// The Brief — Service Worker
// Caches the app shell for offline use and fast repeat loads

const CACHE   = "the-brief-v2-2026-04-14";
const ASSETS  = [
  "./index.html",
  "./manifest.json",
  "./icon-192.png",
  "./icon-512.png"
];

// Install: pre-cache core assets
self.addEventListener("install", e => {
  e.waitUntil(
    caches.open(CACHE).then(c => c.addAll(ASSETS))
  );
  self.skipWaiting();
});

// Activate: clean up old caches
self.addEventListener("activate", e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

// Fetch: network-first for HTML and CDN scripts, cache-first for local assets
self.addEventListener("fetch", e => {
  const url = new URL(e.request.url);

  // Network-first for HTML (daily updates)
  const isHTML = url.pathname.endsWith("index.html") || url.pathname.endsWith("/") || url.pathname.endsWith("the-brief.html");
  // Network-first for CDN scripts (security patches)
  const isCDN = url.hostname.includes("unpkg.com") || url.hostname.includes("cdn.jsdelivr.net");

  if (isHTML || isCDN) {
    e.respondWith(
      fetch(e.request)
        .then(res => {
          const clone = res.clone();
          caches.open(CACHE).then(c => c.put(e.request, clone));
          return res;
        })
        .catch(() => caches.match(isHTML ? "./index.html" : e.request))
    );
    return;
  }

  // Cache-first for local assets (icons, manifest)
  e.respondWith(
    caches.match(e.request).then(cached => {
      if (cached) return cached;
      return fetch(e.request).then(res => {
        if (res.ok) {
          const clone = res.clone();
          caches.open(CACHE).then(c => c.put(e.request, clone));
        }
        return res;
      });
    })
  );
});
