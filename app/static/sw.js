/**
 * Service Worker — Offline support for AI Personal Assistant
 * Cache-first for static assets, network-first for API with fallback.
 * IndexedDB persistence + Background Sync for offline mutations.
 */
const CACHE_VERSION = 'v57';
const STATIC_CACHE = `static-${CACHE_VERSION}`;
const API_CACHE = `api-${CACHE_VERSION}`;

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
  '/api/v1/templates',
];

// ─── IndexedDB Helpers ───
const IDB_NAME = 'aia-offline-store';
const IDB_VERSION = 1;
const STORE_API = 'api-cache';
const STORE_QUEUE = 'mutation-queue';

function openIDB() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(IDB_NAME, IDB_VERSION);
    req.onupgradeneeded = (e) => {
      const db = e.target.result;
      if (!db.objectStoreNames.contains(STORE_API)) {
        db.createObjectStore(STORE_API, { keyPath: 'url' });
      }
      if (!db.objectStoreNames.contains(STORE_QUEUE)) {
        db.createObjectStore(STORE_QUEUE, { keyPath: 'id', autoIncrement: true });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function idbPut(storeName, data) {
  const db = await openIDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(storeName, 'readwrite');
    tx.objectStore(storeName).put(data);
    tx.oncomplete = () => { db.close(); resolve(); };
    tx.onerror = () => { db.close(); reject(tx.error); };
  });
}

async function idbGet(storeName, key) {
  const db = await openIDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(storeName, 'readonly');
    const req = tx.objectStore(storeName).get(key);
    req.onsuccess = () => { db.close(); resolve(req.result); };
    req.onerror = () => { db.close(); reject(req.error); };
  });
}

async function idbGetAll(storeName) {
  const db = await openIDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(storeName, 'readonly');
    const req = tx.objectStore(storeName).getAll();
    req.onsuccess = () => { db.close(); resolve(req.result); };
    req.onerror = () => { db.close(); reject(req.error); };
  });
}

async function idbDelete(storeName, key) {
  const db = await openIDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(storeName, 'readwrite');
    tx.objectStore(storeName).delete(key);
    tx.oncomplete = () => { db.close(); resolve(); };
    tx.onerror = () => { db.close(); reject(tx.error); };
  });
}

// ─── Install: Pre-cache static assets ───
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE).then((cache) => {
      return cache.addAll(PRECACHE).catch(() => {});
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
    if (request.mode === 'navigate') {
      const cached = await caches.match('/');
      if (cached) return cached;
    }
    return new Response('Offline', { status: 503 });
  }
}

// ─── Network-first with cache fallback + IndexedDB persistence ───
async function networkFirstAPI(request) {
  const isCacheable = CACHEABLE_API.some((p) => request.url.includes(p));
  try {
    const response = await fetch(request);
    if (response.ok && isCacheable) {
      // Cache in both Cache API and IndexedDB
      const cache = await caches.open(API_CACHE);
      cache.put(request, response.clone());
      try {
        const data = await response.clone().json();
        await idbPut(STORE_API, { url: request.url, data, timestamp: Date.now() });
      } catch (e) { /* skip non-JSON */ }
    }
    return response;
  } catch {
    // Offline: try Cache API first, then IndexedDB
    if (isCacheable) {
      const cached = await caches.match(request);
      if (cached) return cached;
      try {
        const entry = await idbGet(STORE_API, request.url);
        if (entry && entry.data) {
          return new Response(JSON.stringify(entry.data), {
            headers: { 'Content-Type': 'application/json', 'X-From-IDB': 'true' }
          });
        }
      } catch (e) { /* IndexedDB failed too */ }
    }
    return new Response(JSON.stringify({ error: 'offline', cached: false }), {
      status: 503,
      headers: { 'Content-Type': 'application/json' },
    });
  }
}

// ─── Queue mutations in IndexedDB for offline sync ───
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
    await idbPut(STORE_QUEUE, item);
    // Register background sync
    if (self.registration.sync) {
      await self.registration.sync.register('replay-mutations');
    }
    // Notify page of queue change
    const queueItems = await idbGetAll(STORE_QUEUE);
    const bc = new BroadcastChannel('sw-messages');
    bc.postMessage({ type: 'queue-updated', count: queueItems.length });
    bc.close();
  } catch (e) {
    console.error('Queue failed:', e);
  }
}

// ─── Background Sync: Replay queued mutations ───
self.addEventListener('sync', (event) => {
  if (event.tag === 'replay-mutations') {
    event.waitUntil(replayMutations());
  }
});

async function replayMutations() {
  let items;
  try {
    items = await idbGetAll(STORE_QUEUE);
  } catch { return; }
  if (!items.length) return;

  items.sort((a, b) => a.timestamp - b.timestamp);
  let successCount = 0;

  for (const item of items) {
    try {
      const response = await fetch(item.url, {
        method: item.method,
        headers: item.headers,
        body: item.body || undefined,
      });
      if (response.ok || response.status < 500) {
        await idbDelete(STORE_QUEUE, item.id);
        successCount++;
      }
    } catch {
      break; // Network still down
    }
  }

  // Notify page
  const remaining = await idbGetAll(STORE_QUEUE);
  const bc = new BroadcastChannel('sw-messages');
  bc.postMessage({
    type: 'sync-complete',
    synced: successCount,
    remaining: remaining.length,
  });
  bc.close();
}

// ─── Listen for messages from page ───
self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
  if (event.data && event.data.type === 'GET_QUEUE_COUNT') {
    idbGetAll(STORE_QUEUE).then(items => {
      const bc = new BroadcastChannel('sw-messages');
      bc.postMessage({ type: 'queue-updated', count: items.length });
      bc.close();
    }).catch(() => {});
  }
  if (event.data && event.data.type === 'FORCE_SYNC') {
    replayMutations();
  }
});

// ─── Push Notification Handler ───
self.addEventListener('push', (event) => {
  let data = { title: 'AI Assistant', body: 'New notification', url: '/' };
  try {
    if (event.data) data = Object.assign(data, event.data.json());
  } catch (e) {
    if (event.data) data.body = event.data.text();
  }
  const options = {
    body: data.body,
    icon: data.icon || '/favicon.ico',
    badge: data.badge || '/favicon.ico',
    data: { url: data.url || '/' },
    tag: data.tag || 'aia-notification',
    renotify: true,
    requireInteraction: false,
  };
  event.waitUntil(self.registration.showNotification(data.title, options));
});

// ─── Notification Click Handler ───
self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const url = event.notification.data?.url || '/';
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then((windowClients) => {
      for (const client of windowClients) {
        if (client.url.includes(self.location.origin) && 'focus' in client) {
          return client.focus();
        }
      }
      return clients.openWindow(url);
    })
  );
});
