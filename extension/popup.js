/* tk — popup logic */
'use strict';

const DEFAULT_SERVER = 'http://127.0.0.1:8765';

const $ = (sel) => document.querySelector(sel);

function getServer() {
  return new Promise((resolve) => {
    try {
      chrome.storage.local.get('server', (data) => {
        resolve(((data && data.server) || DEFAULT_SERVER).replace(/\/+$/, ''));
      });
    } catch (_) { resolve(DEFAULT_SERVER); }
  });
}

function setServer(url) {
  return new Promise((resolve) => {
    try {
      chrome.storage.local.set({ server: url }, () => resolve(true));
    } catch (_) { resolve(false); }
  });
}

async function pingServer() {
  const status = $('#status');
  const url = await getServer();
  status.className = 'status';
  status.textContent = 'Checking…';
  try {
    const r = await fetch(url + '/api/version', { method: 'GET' });
    if (r.ok) {
      let label = 'Connected ✓';
      try {
        const data = await r.json();
        if (data && data.version) label = 'Connected ✓ (tk ' + data.version + ')';
      } catch (_) {}
      status.className = 'status ok';
      status.textContent = label;
    } else {
      status.className = 'status bad';
      status.textContent = 'Not running ✗ (HTTP ' + r.status + ')';
    }
  } catch (_) {
    status.className = 'status bad';
    status.textContent = 'Not running ✗';
  }
}

function formatTime(ts) {
  try {
    const d = new Date(ts);
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  } catch (_) { return ''; }
}

function loadSelections() {
  try {
    chrome.storage.local.get(null, (data) => {
      const items = [];
      for (const k in data) {
        if (k.indexOf('sel:') === 0) {
          items.push(Object.assign({ _key: k }, data[k]));
        }
      }
      items.sort((a, b) => (b.ts || 0) - (a.ts || 0));
      const top = items.slice(0, 3);
      const list = $('#selections');
      const empty = $('#selections-empty');
      list.innerHTML = '';
      if (top.length === 0) {
        empty.style.display = 'block';
        return;
      }
      empty.style.display = 'none';
      top.forEach((it) => {
        const li = document.createElement('li');
        const text = document.createElement('div');
        text.className = 'text';
        text.textContent = (it.text || '').slice(0, 200) + '  · ' + formatTime(it.ts);
        const link = document.createElement('a');
        link.textContent = 'Re-send';
        link.href = '#';
        link.addEventListener('click', async (e) => {
          e.preventDefault();
          try {
            await navigator.clipboard.writeText(it.text || '');
            link.textContent = 'Copied!';
            setTimeout(() => { link.textContent = 'Re-send'; }, 1200);
          } catch (_) {
            link.textContent = 'Copy failed';
          }
        });
        li.appendChild(text);
        li.appendChild(link);
        list.appendChild(li);
      });
    });
  } catch (_) {}
}

document.addEventListener('DOMContentLoaded', async () => {
  const input = $('#server-input');
  const url = await getServer();
  input.value = url;

  input.addEventListener('change', async () => {
    const v = (input.value || '').trim().replace(/\/+$/, '') || DEFAULT_SERVER;
    await setServer(v);
    input.value = v;
    pingServer();
  });

  $('#open-btn').addEventListener('click', async () => {
    const u = await getServer();
    try { chrome.tabs.create({ url: u }); } catch (_) {}
  });

  pingServer();
  loadSelections();
});
