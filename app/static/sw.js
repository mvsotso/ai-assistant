/**
 * Service Worker — Offline support for AI Personal Assistant
 * Cache-first for static assets, network-first for API with fallback.
 */
const CACHE_VERSION = 'v1';
const STATIC_CACHE = `static-${CACHE_VERSION}`;
const API_CACHE = `api-${CACHE_VERSION}`;
const QUEUE_STORE = 'offline-queue';

// Static assets to pre-cache
const PRECACHE = [
  '/',
  'https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Noto+Sans+Khmer:wght@400;500;600;700;800&family=Outfit:wght@600;700;800&display=swap',
];

// API paths to cache responses for offline fallback
const CACHEABLE_API = [
  '/api/v1/tasks',
  '/api/v1/board',
  '/api/v1/dashboard',
  '/api/v1/team',
  '/api/v1/team/stats',
  '/api/v1/reminders',
  '/api/v1/categories',
  '/api/v1/task-groups',
  '/api/v1/notifications/count',
];

// ─── Install: Pre-cache static assets ───
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE).then((cache) => {
      return cache.addAll(PRECACHE).catch(() => {
        // Silently fail pre-cache if offline during install
      });
    })
  );
  self.skipWaiting();
});

// ─── Activate: Clean old caches ───
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.filter((k) => k !== STATIC_CACHE && k !== API_CACHE).map((k) => caches.delete(k))
      );
    })
  );
  self.clients.claim();
});

// ─── Fetch: Strategy based on request type ───
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // Skip non-GET requests — queue mutations for offline sync
  if (event.request.method !== 'GET') {
    if (!navigator.onLine && url.pathname.startsWith('/api/')) {
      event.respondWith(
        queueRequest(event.request).then(() => {
          return new Response(JSON.stringify({ queued: true, offline: true }), {
            headers: { 'Content-Type': 'application/json' },
          });
        })
      );
    }
    return;
  }

  // API requests: Network-first with cache fallback
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(networkFirstAPI(event.request));
    return;
  }

  // Static assets & pages: Cache-first
  event.respondWith(cacheFirst(event.request));
});

// ─── Cache-first strategy ───
async function cacheFirst(request) {
  const cached = await caches.match(request);
  if (cached) return cached;
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(STATIC_CACHE);
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    // Return offline fallback for navigation
    if (request.mode === 'navigate') {
      const cached = await caches.match('/');
      if (cached) return cached;
    }
    return new Response('Offline', { status: 503 });
  }
}

// ─── Network-first with cache fallback for API ───
async function networkFirstAPI(request) {
  const isCacheable = CACHEABLE_API.some((p) => request.url.includes(p));
  try {
    const response = await fetch(request);
    // Cache successful API responses
    if (response.ok && isCacheable) {
      const cache = await caches.open(API_CACHE);
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    // Offline: try cache
    if (isCacheable) {
      const cached = await caches.match(request);
      if (cached) return cached;
    }
    return new Response(JSON.stringify({ error: 'offline', cached: false }), {
      status: 503,
      headers: { 'Content-Type': 'application/json' },
    });
  }
}

// ─── Queue failed mutations for offline sync ───
async function queueRequest(request) {
  try {
    const body = await request.clone().text();
    const item = {
      url: request.url,
      method: request.method,
      headers: Object.fromEntries(request.headers.entries()),
      body: body,
      timestamp: Date.now(),
    };
    // Use BroadcastChannel to notify the page
    const bc = new BroadcastChannel('sw-messages');
    bc.postMessage({ type: 'queued', item });
    bc.close();
  } catch (e) {
    // Silently fail queue
  }
}

// ─── Listen for sync messages from the page ───
self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
});
