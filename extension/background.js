/* tk — Send to Toolkit — MV3 service worker
 *
 * Context menus:
 *   - Send image to tk workspace        (downloads the image via chrome.downloads)
 *   - Send link to tk download queue    (fetches and uploads to /api/upload)
 *   - Run text through tk → text/json   (stores selection in chrome.storage.local)
 */
'use strict';

const DEFAULT_SERVER = 'http://127.0.0.1:8765';

const MENU_IDS = {
  IMAGE: 'tk-send-image',
  LINK: 'tk-send-link',
  SELECTION: 'tk-send-selection',
};

// ---------- helpers ----------
function getServer() {
  return new Promise((resolve) => {
    try {
      chrome.storage.local.get('server', (data) => {
        const v = (data && data.server) || DEFAULT_SERVER;
        resolve(String(v).replace(/\/+$/, ''));
      });
    } catch (_) {
      resolve(DEFAULT_SERVER);
    }
  });
}

function log() {
  try { console.log.apply(console, ['[tk]'].concat([].slice.call(arguments))); } catch (_) {}
}

// ---------- install: create menus ----------
chrome.runtime.onInstalled.addListener(() => {
  try { chrome.contextMenus.removeAll(); } catch (_) {}

  chrome.contextMenus.create({
    id: MENU_IDS.IMAGE,
    title: 'Send image to tk workspace',
    contexts: ['image'],
  });
  chrome.contextMenus.create({
    id: MENU_IDS.LINK,
    title: 'Send link to tk download queue',
    contexts: ['link'],
  });
  chrome.contextMenus.create({
    id: MENU_IDS.SELECTION,
    title: 'Run text through tk → text/json',
    contexts: ['selection'],
  });
});

// ---------- click handler ----------
chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  const server = await getServer();

  // -- IMAGE: trigger a download of the source image
  if (info.menuItemId === MENU_IDS.IMAGE && info.srcUrl) {
    try {
      chrome.downloads.download({ url: info.srcUrl }, (id) => {
        if (chrome.runtime.lastError) {
          log('image download failed:', chrome.runtime.lastError.message);
        } else {
          log('image queued for download, id=', id, info.srcUrl);
        }
      });
    } catch (e) {
      log('image download error:', e);
    }
    return;
  }

  // -- LINK: fetch and POST as multipart to /api/upload
  if (info.menuItemId === MENU_IDS.LINK && info.linkUrl) {
    try {
      const resp = await fetch(info.linkUrl);
      if (!resp.ok) throw new Error('fetch failed: ' + resp.status);
      const blob = await resp.blob();
      const url = new URL(info.linkUrl);
      const name = decodeURIComponent((url.pathname.split('/').pop() || 'download').trim()) || 'download';
      const fd = new FormData();
      fd.append('file', blob, name);
      const upload = await fetch(server + '/api/upload', { method: 'POST', body: fd });
      log('link uploaded:', name, '->', upload.status);
    } catch (e) {
      log('link upload error:', e);
    }
    return;
  }

  // -- SELECTION: store text in local storage, then open popup
  if (info.menuItemId === MENU_IDS.SELECTION && info.selectionText) {
    const ts = Date.now();
    const key = 'sel:' + ts;
    try {
      const item = {};
      item[key] = {
        text: info.selectionText,
        ts: ts,
        pageUrl: info.pageUrl || (tab && tab.url) || '',
      };
      chrome.storage.local.set(item, () => log('selection stored:', key));
    } catch (e) {
      log('selection store error:', e);
    }
    try {
      // Programmatic popup open requires user gesture; this typically no-ops in MV3 SW.
      if (chrome.action && chrome.action.openPopup) {
        chrome.action.openPopup().catch(() => {});
      }
    } catch (_) {}
  }
});

// First-run default for server URL
chrome.runtime.onInstalled.addListener(() => {
  try {
    chrome.storage.local.get('server', (data) => {
      if (!data || !data.server) {
        chrome.storage.local.set({ server: DEFAULT_SERVER });
      }
    });
  } catch (_) {}
});
