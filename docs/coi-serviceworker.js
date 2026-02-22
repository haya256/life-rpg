/**
 * coi-serviceworker
 * GitHub Pages で SharedArrayBuffer を有効にするためのサービスワーカー。
 * 同一オリジンのレスポンスに COOP / COEP ヘッダーを付加します。
 */

self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (event) => event.waitUntil(self.clients.claim()));

self.addEventListener('fetch', (event) => {
  // only-if-cached はクロスオリジンでは使えないのでスキップ
  if (event.request.cache === 'only-if-cached' && event.request.mode !== 'same-origin') {
    return;
  }

  event.respondWith(
    fetch(event.request)
      .then((response) => {
        const url = new URL(event.request.url);

        // クロスオリジンのリソース（CDN 等）はそのまま返す
        if (url.origin !== self.location.origin) return response;
        if (response.status === 0) return response;

        const newHeaders = new Headers(response.headers);
        newHeaders.set('Cross-Origin-Opener-Policy', 'same-origin');
        // credentialless: CDN リソースを CORP ヘッダーなしで読み込める
        newHeaders.set('Cross-Origin-Embedder-Policy', 'credentialless');

        return new Response(response.body, {
          status: response.status,
          statusText: response.statusText,
          headers: newHeaders,
        });
      })
      .catch((err) => console.error('[coi-serviceworker]', err))
  );
});
