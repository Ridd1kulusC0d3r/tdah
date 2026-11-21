// Agora — service worker: guarda o app para funcionar sem internet e recebe lembretes com o app fechado.
// A API nunca é guardada em cache. As notificações chegam sem conteúdo (Web Push "vazio"): o service worker
// busca o texto no servidor do Agora, provando que é dono da inscrição. Nenhum texto passa pelo serviço de push.
const CACHE = "agora-v20";
const ARQ = ["./", "./index.html", "./manifest.webmanifest", "./config.js", "./icon.svg", "./fonts/fonts.css", "./fonts/next-latin.woff2", "./fonts/next-latin-ext.woff2", "./fonts/mono-400.woff2", "./fonts/mono-600.woff2", "./icon-192.png", "./icon-512.png"];
self.addEventListener("install", e => e.waitUntil(caches.open(CACHE).then(c => c.addAll(ARQ)).then(() => self.skipWaiting())));
self.addEventListener("activate", e => e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim())));
self.addEventListener("fetch", e => {
  const u = new URL(e.request.url);
  if (e.request.method !== "GET" || u.pathname.includes("/api/") || u.pathname.includes("checkout") || u.pathname.includes("admin") || u.origin !== location.origin) return;
  e.respondWith(fetch(e.request).then(r => { const cp = r.clone(); caches.open(CACHE).then(c => c.put(e.request, cp)); return r; }).catch(() => caches.match(e.request)));
});
self.addEventListener("push", e => e.waitUntil((async () => {
  let msgs = [];
  try {
    const sub = await self.registration.pushManager.getSubscription();
    const j = sub && sub.toJSON();
    if (j) {
      const r = await fetch(new URL("../api/push/pendentes", self.registration.scope), { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ endpoint: j.endpoint, auth: j.keys && j.keys.auth }) });
      if (r.ok) msgs = (await r.json()).mensagens || [];
    }
  } catch (_) {}
  if (!msgs.length) msgs = [{ titulo: "Agora", corpo: "Você tem um lembrete. Toque para abrir.", url: "./" }];
  await Promise.all(msgs.map((m, i) => self.registration.showNotification(m.titulo || "Agora", { body: m.corpo || "", icon: "icon-192.png", badge: "icon-192.png", tag: "agora-" + i + "-" + Date.now(), data: { url: m.url || "./" } })));
})()));
self.addEventListener("notificationclick", e => {
  e.notification.close();
  const alvo = new URL((e.notification.data && e.notification.data.url) || "./", self.registration.scope).href;
  e.waitUntil(self.clients.matchAll({ type: "window", includeUncontrolled: true }).then(cs => {
    const c = cs.find(x => x.url.startsWith(self.registration.scope));
    if (c) { c.navigate(alvo).catch(() => {}); return c.focus(); }
    return self.clients.openWindow(alvo);
  }));
});
