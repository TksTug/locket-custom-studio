// Service Worker for Locket Custom Studio PWA
const CACHE_NAME = 'locket-studio-v17';
const ASSETS_TO_CACHE = [
  '/',
  '/manifest.json',
  '/icon-192.png',
  '/icon-512.png'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(ASSETS_TO_CACHE).catch((err) => {
        console.warn('SW cache.addAll warning:', err);
      });
    })
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.map((key) => {
          if (key !== CACHE_NAME) {
            return caches.delete(key);
          }
        })
      );
    })
  );
  self.clients.claim();
});

// Helper: Fetch with timeout
function fetchWithTimeout(request, timeoutMs = 7000) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('NETWORK_TIMEOUT')), timeoutMs);
    fetch(request)
      .then((res) => {
        clearTimeout(timer);
        resolve(res);
      })
      .catch((err) => {
        clearTimeout(timer);
        reject(err);
      });
  });
}

self.addEventListener('fetch', (event) => {
  // Dynamic API requests: pass directly to network
  if (event.request.url.includes('/api/')) {
    event.respondWith(fetch(event.request));
    return;
  }

  // Navigation / HTML page requests: Network-first with fast timeout fallback to cached app shell
  if (
    event.request.mode === 'navigate' ||
    event.request.url.endsWith('/') ||
    event.request.url.includes('index.html')
  ) {
    event.respondWith(
      fetchWithTimeout(event.request, 6000)
        .then((response) => {
          if (response && response.status === 200) {
            const clone = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
          }
          return response;
        })
        .catch(async () => {
          // If server is cold-starting or offline, serve cached app shell instantly!
          const match = (await caches.match(event.request)) || (await caches.match('/'));
          if (match) return match;
          return fetch(event.request);
        })
    );
    return;
  }

  // Static assets: Cache-first fallback to network
  event.respondWith(
    caches.match(event.request).then((response) => {
      return (
        response ||
        fetch(event.request).then((netRes) => {
          if (netRes && netRes.status === 200) {
            const clone = netRes.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
          }
          return netRes;
        })
      );
    })
  );
});
