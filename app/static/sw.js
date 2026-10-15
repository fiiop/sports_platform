const VERSION = '__ASSET_VERSION__';
const CACHE = `campus-move-public-${VERSION}`;
const PATHS = ['/static/style.css', '/static/app.js', '/static/buddies.js', '/static/vendor/leaflet/leaflet.js', '/static/vendor/leaflet/leaflet.css', '/static/offline.html', '/static/manifest.webmanifest', '/static/icon-192.png', '/static/icon-512.png'];
const PUBLIC = PATHS.map(path => `${path}?v=${VERSION}`);
self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(PUBLIC)));
});
self.addEventListener('activate', event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(key => key.startsWith('campus-move-public-') && key !== CACHE).map(key => caches.delete(key)))).then(() => self.clients.claim()));
});
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);
  // Never cache APIs, authenticated HTML or mutations.
  if (event.request.method !== 'GET' || url.origin !== self.location.origin || url.pathname.startsWith('/api/')) return;
  if (event.request.mode === 'navigate') {
    event.respondWith(fetch(event.request).catch(() => caches.match(`/static/offline.html?v=${VERSION}`)));
    return;
  }
  if (PATHS.includes(url.pathname)) {
    event.respondWith(fetch(event.request).then(response => {
      if (response.ok) {const copy = response.clone();event.waitUntil(caches.open(CACHE).then(cache => cache.put(event.request, copy)));}
      return response;
    }).catch(() => caches.match(event.request)));
  }
});
