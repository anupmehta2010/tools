/* tk — Personal Toolkit — PWA registrar
 * Tiny shim that registers the service worker and captures the install prompt.
 */
(function () {
  'use strict';

  if ('serviceWorker' in navigator) {
    window.addEventListener('load', function () {
      navigator.serviceWorker
        .register('/static/sw.js', { scope: '/' })
        .then(function (reg) {
          try { console.log('[tk] service worker registered:', reg.scope); } catch (_) {}
        })
        .catch(function (err) {
          try { console.log('[tk] service worker registration failed:', err); } catch (_) {}
        });
    });
  }

  // Capture the beforeinstallprompt event so the UI can fire it on demand.
  window.tkInstallPrompt = null;
  window.addEventListener('beforeinstallprompt', function (e) {
    e.preventDefault();
    window.tkInstallPrompt = e;
    try { console.log('[tk] install prompt captured — call window.tkInstallPrompt.prompt() to show.'); } catch (_) {}
    try {
      window.dispatchEvent(new CustomEvent('tk:installable'));
    } catch (_) {}
  });

  window.addEventListener('appinstalled', function () {
    window.tkInstallPrompt = null;
    try { console.log('[tk] app installed'); } catch (_) {}
  });
})();
