/* tk — Personal Toolkit — Service Worker
 *
 * Strategies:
 *   /api/*           -> network only (never cache)
 *   static assets    -> stale-while-revalidate
 *   navigation reqs  -> network first, fall back to cached "/"
 */
'use strict';

const CACHE_NAME = 'tk-shell-v1';

const PRECACHE_URLS = [
  '/',
  '/static/style.css',
  '/static/app.js',
  '/static/manifest.json',
];

// ---------- install ----------
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      // Use addAll best-effort — a single bad URL shouldn't kill install.
      return Promise.all(
        PRECACHE_URLS.map((url) =>
          cache.add(new Request(url, { cache: 'reload' })).catch(() => null)
        )
      );
    }).then(() => self.skipWaiting())
  );
});

// ---------- activate (clean old caches) ----------
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((k) => k.startsWith('tk-shell-') && k !== CACHE_NAME)
          .map((k) => caches.delete(k))
      )
    ).then(() => self.clients.claim())
  );
});

// ---------- helpers ----------
function isSameOrigin(url) {
  try { return new URL(url).origin === self.location.origin; }
  catch (_) { return false; }
}

function isApiPath(url) {
  try { return new URL(url).pathname.startsWith('/api/'); }
  catch (_) { return false; }
}

function isStaticPath(url) {
  try {
    const p = new URL(url).pathname;
    return p.startsWith('/static/') || p === '/favicon.ico';
  } catch (_) { return false; }
}

async function staleWhileRevalidate(request) {
  const cache = await caches.open(CACHE_NAME);
  const cached = await cache.match(request);
  const networkPromise = fetch(request)
    .then((response) => {
      if (response && response.status === 200 && response.type !== 'opaque') {
        cache.put(request, response.clone()).catch(() => {});
      }
      return response;
    })
    .catch(() => null);
  return cached || (await networkPromise) || new Response('', { status: 504 });
}

async function networkFirstNav(request) {
  try {
    const response = await fetch(request);
    return response;
  } catch (_) {
    const cache = await caches.open(CACHE_NAME);
    const fallback = await cache.match('/');
    return fallback || new Response('Offline', { status: 503, statusText: 'Offline' });
  }
}

// ---------- fetch handler ----------
self.addEventListener('fetch', (event) => {
  const req = event.request;

  // Only handle GET — let everything else fall through to the network.
  if (req.method !== 'GET') return;

  // Never cache the API.
  if (isSameOrigin(req.url) && isApiPath(req.url)) {
    event.respondWith(fetch(req));
    return;
  }

  // Navigation: network first, fall back to cached shell.
  if (req.mode === 'navigate') {
    event.respondWith(networkFirstNav(req));
    return;
  }

  // Static assets: stale-while-revalidate.
  if (isSameOrigin(req.url) && isStaticPath(req.url)) {
    event.respondWith(staleWhileRevalidate(req));
    return;
  }

  // Other same-origin GETs: try network, fall back to cache if available.
  if (isSameOrigin(req.url)) {
    event.respondWith(
      fetch(req).catch(() =>
        caches.match(req).then((r) => r || new Response('', { status: 504 }))
      )
    );
  }
});
