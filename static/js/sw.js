// Acquacotta service worker: pass-through only.
//
// It exists because Chrome requires a service worker with a fetch handler before
// it offers to install the app, and only an installed app appears in Android's
// share sheet. It caches nothing: every request goes to the network exactly as
// if there were no worker, so a deploy is live on the next load and a stale
// build can never be served. Offline support stays in IndexedDB (storage.js).

self.addEventListener('install', () => self.skipWaiting());

self.addEventListener('activate', (event) => {
    event.waitUntil(self.clients.claim());
});

self.addEventListener('fetch', (event) => {
    // Cross-origin requests (CDN scripts, Google sign-in) never touch the worker.
    if (new URL(event.request.url).origin !== self.location.origin) return;
    event.respondWith(fetch(event.request));
});
