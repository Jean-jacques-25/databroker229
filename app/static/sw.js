// Service Worker — LaCentraleDesDonnees229 PWA
const CACHE_NAME = 'lcdd229-v1';
const STATIC_ASSETS = [
  '/',
  '/login',
  '/static/logo.png',
  '/static/favicon.ico',
  '/offline'
];

// Installation : mettre en cache les ressources statiques
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => {
      console.log('PWA: Cache ouvert');
      return cache.addAll(STATIC_ASSETS.filter(url => url !== '/offline'));
    })
  );
  self.skipWaiting();
});

// Activation : nettoyer les anciens caches
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

// Fetch : strategie network-first avec fallback cache
self.addEventListener('fetch', event => {
  // Ne pas intercepter les requetes POST ou API
  if (event.request.method !== 'GET') return;
  if (event.request.url.includes('/api/')) return;
  if (event.request.url.includes('/admin/')) return;

  event.respondWith(
    fetch(event.request)
      .then(response => {
        // Mettre en cache la reponse fraiche
        if (response.ok) {
          const clone = response.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
        }
        return response;
      })
      .catch(() => {
        // Fallback sur le cache si hors ligne
        return caches.match(event.request).then(cached => {
          return cached || caches.match('/login');
        });
      })
  );
});

// Notifications push (pour plus tard)
self.addEventListener('push', event => {
  if (!event.data) return;
  const data = event.data.json();
  self.registration.showNotification(data.title || 'LaCentraleDesDonnees229', {
    body: data.body || 'Nouvelle notification',
    icon: '/static/logo.png',
    badge: '/static/favicon.ico',
    data: { url: data.url || '/' }
  });
});

self.addEventListener('notificationclick', event => {
  event.notification.close();
  event.waitUntil(clients.openWindow(event.notification.data.url));
});
