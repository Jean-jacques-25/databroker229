// Service Worker minimal pour valider les critères PWA
self.addEventListener('install', function(event) {
    console.log('[Service Worker] Installing Service Worker...');
});

self.addEventListener('activate', function(event) {
    console.log('[Service Worker] Activating Service Worker...');
    return self.clients.claim();
});

self.addEventListener('fetch', function(event) {
    // Laisse les requêtes passer normalement vers le serveur Flask
    event.respondWith(fetch(event.request));
});
