// Service worker do Meu Fla.
//
// Estratégia: rede primeiro em tudo, cache como reserva.
//
// O cache existe para o app abrir sem internet, não para economizar rede. Se
// o shell fosse cache primeiro, uma versão nova do index.html só apareceria
// na abertura seguinte. Com rede primeiro, abrir o app já traz a versão atual;
// se a rede demorar mais que TEMPO_LIMITE ou falhar, entra o que está guardado.
const VERSION = "meu-fla-v11";
const SHELL = ["./", "./index.html", "./manifest.json", "./icons/icon-192.png", "./icons/icon-512.png", "./icons/escudo.png"];
const TEMPO_LIMITE = 3000;

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(VERSION).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((chaves) => Promise.all(chaves.filter((k) => k !== VERSION).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

// Busca na rede ignorando o cache HTTP do navegador (o GitHub Pages manda
// guardar por 10 minutos, o que atrasaria uma publicação recém-feita).
async function daRede(req, chave) {
  const controle = new AbortController();
  const relogio = setTimeout(() => controle.abort(), TEMPO_LIMITE);
  try {
    const res = await fetch(new Request(req, { cache: "reload" }), { signal: controle.signal });
    if (res.ok) {
      const copia = res.clone();
      caches.open(VERSION).then((c) => c.put(chave, copia));
    }
    return res;
  } finally {
    clearTimeout(relogio);
  }
}

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  // A API da ESPN não entra no cache: placar velho é pior que nenhum placar.
  if (url.hostname.endsWith("espn.com")) return;
  const mesmaOrigem = url.origin === self.location.origin;
  if (!mesmaOrigem) return;

  // O app põe ?timestamp nos JSON para furar o cache do navegador. No cache do
  // service worker a chave é a URL sem query, senão cada atualização deixaria
  // uma entrada nova para sempre.
  const chave = url.origin + url.pathname;

  event.respondWith(
    daRede(req, chave).catch(() =>
      caches.match(chave).then((guardado) => guardado || caches.match("./index.html"))
    )
  );
});
