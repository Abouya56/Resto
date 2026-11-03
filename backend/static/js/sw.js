/* Service worker de Resto : rend l'app installable et affiche une page claire sans internet.
   Il ne garde AUCUNE page en mémoire (commandes, stocks, comptes : tout reste privé et à jour).
   Il garde seulement la page « hors connexion » et les fichiers de style, script et image du site. */
const VERSION = "resto-v2";
const STATIC_CACHE = `${VERSION}-static`;
const OFFLINE_URL = "/hors-ligne/";

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE).then((cache) => cache.add(new Request(OFFLINE_URL, { cache: "reload" }))).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((key) => !key.startsWith(VERSION)).map((key) => caches.delete(key))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  // Pages : toujours le réseau. Sans internet, on montre la page « hors connexion ».
  if (request.mode === "navigate") {
    event.respondWith(fetch(request).catch(() => caches.match(OFFLINE_URL)));
    return;
  }

  // Fichiers du site (versionnés par ?v=…) : servis vite depuis la mémoire, mis à jour en arrière-plan.
  if (url.pathname.startsWith("/static/")) {
    event.respondWith(
      caches.open(STATIC_CACHE).then((cache) =>
        cache.match(request).then((cached) => {
          const fresh = fetch(request)
            .then((response) => {
              if (response.ok) cache.put(request, response.clone());
              return response;
            })
            .catch(() => cached);
          return cached || fresh;
        })
      )
    );
  }
});
