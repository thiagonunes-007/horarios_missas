// Service Worker do app "Horário de Missas".
// Objetivo: (1) tornar o site instalável como PWA (exigência do Chrome para
// o prompt de instalação e para o empacotamento em Trusted Web Activity no
// Google Play) e (2) evitar tela em branco quando o usuário abre o app sem
// internet, servindo o último "app shell" salvo em cache.
//
// Importante: os dados (dados/*.csv e o Google Sheets/proxies) sempre
// tentam a rede primeiro — o cache só entra em ação se o dispositivo estiver
// offline, nunca para "economizar" uma requisição que teria sucesso.

const CACHE_VERSION = "v2";
const CACHE_NAME = "missas-app-shell-" + CACHE_VERSION;

const APP_SHELL = [
  "./",
  "./index.html",
  "./manifest.json",
  "./logo.png",
  "./icons/icon-192.png",
  "./icons/icon-512.png",
  "./icons/icon-192-maskable.png",
  "./icons/icon-512-maskable.png"
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => cache.addAll(APP_SHELL))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((names) => Promise.all(
        names.filter((n) => n !== CACHE_NAME).map((n) => caches.delete(n))
      ))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;

  const url = new URL(req.url);

  // Nunca interceptar chamadas de dados (planilhas Google Sheets, proxies
  // CORS, Analytics) — essas sempre vão direto pra rede.
  const isDataOrThirdParty =
    url.hostname.includes("docs.google.com") ||
    url.hostname.includes("corsproxy.io") ||
    url.hostname.includes("allorigins.win") ||
    url.hostname.includes("codetabs.com") ||
    url.hostname.includes("google-analytics.com") ||
    url.hostname.includes("googletagmanager.com");
  if (isDataOrThirdParty) return;

  // Navegação (abrir/recarregar o app): tenta a rede primeiro, pra sempre
  // pegar a versão mais nova do app; se estiver offline, cai pro cache.
  if (req.mode === "navigate") {
    event.respondWith(
      fetch(req).catch(() => caches.match("./index.html"))
    );
    return;
  }

  // Espelho local dos dados (dados/*.csv, atualizado por Action a cada 6h):
  // rede primeiro (pra nunca mostrar planilha desatualizada com internet
  // disponível), cache só como último recurso quando estiver offline.
  if (url.pathname.includes("/dados/")) {
    event.respondWith(
      fetch(req).then((resp) => {
        if (resp && resp.ok) {
          const clone = resp.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(req, clone));
        }
        return resp;
      }).catch(() => caches.match(req))
    );
    return;
  }

  // Estático do próprio app (ícones, manifest, css/fonts locais): cache
  // primeiro, com atualização em segundo plano (stale-while-revalidate).
  if (url.origin === self.location.origin) {
    event.respondWith(
      caches.match(req).then((cached) => {
        const networkFetch = fetch(req).then((resp) => {
          if (resp && resp.ok) {
            const clone = resp.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(req, clone));
          }
          return resp;
        }).catch(() => cached);
        return cached || networkFetch;
      })
    );
  }
});
