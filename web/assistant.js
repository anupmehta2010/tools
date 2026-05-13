/* tk — AI assistant pane (assistant.js)
   Right-side slide-out chat. Attaches to window.tkAI.
   POSTs to /api/ai/chat. Detects [[run cat:cmd k=v …]] directives and
   surfaces them as one-click "Run this" buttons.
   ------------------------------------------------------------------ */
(function () {
  'use strict';

  const STORAGE_KEY = 'tk-ai-history';
  const MAX_HISTORY = 30;

  const A = {
    initialized: false,
    isOpen: false,
    pane: null,
    messagesEl: null,
    inputEl: null,
    sendBtn: null,
    typingEl: null,
    history: [],
    sending: false,
  };

  // ----- Helpers --------------------------------------------------------
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g,
    c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));

  function toast(msg, kind = 'info') {
    const box = document.getElementById('toasts');
    if (!box) { console.log('[ai]', kind, msg); return; }
    const t = document.createElement('div');
    t.className = `toast ${kind}`;
    t.textContent = msg;
    box.appendChild(t);
    setTimeout(() => t.remove(), 3200);
  }

  function loadHistory() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      A.history = raw ? JSON.parse(raw) : [];
      if (!Array.isArray(A.history)) A.history = [];
    } catch { A.history = []; }
  }

  function saveHistory() {
    try {
      const trimmed = A.history.slice(-MAX_HISTORY);
      A.history = trimmed;
      localStorage.setItem(STORAGE_KEY, JSON.stringify(trimmed));
    } catch { /* quota */ }
  }

  // ----- Build pane -----------------------------------------------------
  function build() {
    let pane = document.querySelector('.ai-pane');
    if (!pane) {
      pane = document.createElement('aside');
      pane.className = 'ai-pane';
      pane.innerHTML = `
        <div class="ai-header">
          <h2>🤖 Ask the toolkit</h2>
          <button type="button" class="ai-clear-btn" title="Clear chat">🗑</button>
          <button type="button" class="ai-close-btn" title="Close (A or Esc)">✕</button>
        </div>
        <div class="ai-messages" id="ai-messages"></div>
        <div class="ai-input-wrap">
          <textarea id="ai-input" rows="1" placeholder="Ask anything… e.g. compress this PDF"></textarea>
          <button type="button" class="ai-send-btn" id="ai-send">Send</button>
        </div>
      `;
      document.body.appendChild(pane);
    }
    A.pane = pane;
    A.messagesEl = pane.querySelector('#ai-messages');
    A.inputEl = pane.querySelector('#ai-input');
    A.sendBtn = pane.querySelector('#ai-send');

    pane.querySelector('.ai-close-btn').addEventListener('click', close);
    pane.querySelector('.ai-clear-btn').addEventListener('click', clearChat);
    A.sendBtn.addEventListener('click', onSend);
    A.inputEl.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        onSend();
      }
    });
    A.inputEl.addEventListener('input', autoResize);

    loadHistory();
    renderMessages();
    A.initialized = true;
  }

  function autoResize() {
    A.inputEl.style.height = 'auto';
    A.inputEl.style.height = Math.min(120, A.inputEl.scrollHeight) + 'px';
  }

  // ----- Rendering ------------------------------------------------------
  function renderMessages() {
    if (!A.messagesEl) return;
    A.messagesEl.innerHTML = '';
    if (!A.history.length) {
      const empty = document.createElement('div');
      empty.className = 'ai-empty';
      empty.innerHTML = `
        <div class="ai-empty-icon">🤖</div>
        <div>Ask anything about the toolkit.</div>
        <div class="ai-hint">e.g. "compress this image to 200KB"<br>"convert file.csv to JSON"<br>"how do I merge PDFs?"</div>
      `;
      A.messagesEl.appendChild(empty);
      return;
    }
    for (const m of A.history) renderMessage(m);
    scrollToBottom();
  }

  function renderMessage(msg) {
    if (msg.role !== 'user' && msg.role !== 'assistant') return;
    const el = document.createElement('div');
    el.className = `ai-msg ${msg.role}`;
    if (msg.role === 'user') {
      el.textContent = msg.content;
    } else {
      // Assistant: parse [[run …]] directives
      const {textHTML, actions} = parseAssistantContent(msg.content || '');
      el.innerHTML = textHTML;
      for (const act of actions) appendAction(el, act);
    }
    A.messagesEl.appendChild(el);
  }

  function appendAction(parent, act) {
    const block = document.createElement('div');
    block.className = 'ai-action-block';
    const cmd = document.createElement('div');
    cmd.className = 'ai-action-cmd';
    const argsStr = Object.entries(act.args).map(([k, v]) => `${k}=${v}`).join(' ');
    cmd.textContent = `tk ${act.cat} ${act.cmd}${argsStr ? ' ' + argsStr : ''}`;
    block.appendChild(cmd);
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'ai-action-btn';
    btn.textContent = '▶ Run this';
    btn.addEventListener('click', () => runAction(act, btn, block));
    block.appendChild(btn);
    parent.appendChild(block);
  }

  // Parse "[[run cat:cmd k=v k="v with space" k2=v2]]" out of assistant text.
  function parseAssistantContent(content) {
    const actions = [];
    // Match [[run …]] non-greedy. Use a permissive regex that allows quoted values.
    const regex = /\[\[\s*run\s+([^\]\n]+?)\s*\]\]/g;
    let lastIdx = 0;
    let parts = [];
    let m;
    while ((m = regex.exec(content)) !== null) {
      if (m.index > lastIdx) parts.push({type: 'text', text: content.slice(lastIdx, m.index)});
      const parsed = parseDirective(m[1]);
      if (parsed) {
        parts.push({type: 'placeholder', idx: actions.length});
        actions.push(parsed);
      } else {
        parts.push({type: 'text', text: m[0]});
      }
      lastIdx = regex.lastIndex;
    }
    if (lastIdx < content.length) parts.push({type: 'text', text: content.slice(lastIdx)});
    const textHTML = parts.map(p => p.type === 'text' ? esc(p.text) : '').join('');
    return {textHTML, actions};
  }

  function parseDirective(body) {
    // First token: "cat:cmd"
    body = body.trim();
    if (!body) return null;
    // Split by whitespace, respecting quoted segments
    const tokens = tokenize(body);
    if (!tokens.length) return null;
    const first = tokens[0];
    if (!first.includes(':')) return null;
    const [cat, cmd] = first.split(':');
    if (!cat || !cmd) return null;
    const args = {};
    for (let i = 1; i < tokens.length; i++) {
      const t = tokens[i];
      const eq = t.indexOf('=');
      if (eq === -1) {
        // Treat as positional arg under `_pos<i>` — server can handle or ignore
        args[`_pos${i}`] = t;
      } else {
        const k = t.slice(0, eq);
        let v = t.slice(eq + 1);
        if ((v.startsWith('"') && v.endsWith('"')) || (v.startsWith("'") && v.endsWith("'"))) {
          v = v.slice(1, -1);
        }
        args[k] = v;
      }
    }
    return {cat, cmd, args};
  }

  function tokenize(s) {
    const out = [];
    let cur = '';
    let q = null;
    for (let i = 0; i < s.length; i++) {
      const ch = s[i];
      if (q) {
        if (ch === q) { cur += ch; q = null; }
        else cur += ch;
      } else if (ch === '"' || ch === "'") {
        q = ch; cur += ch;
      } else if (/\s/.test(ch)) {
        if (cur) { out.push(cur); cur = ''; }
      } else {
        cur += ch;
      }
    }
    if (cur) out.push(cur);
    return out;
  }

  async function runAction(act, btn, block) {
    btn.disabled = true;
    btn.textContent = '⏳ Running…';
    // Strip _posN keys before sending; server may not understand them in args.
    const cleanArgs = {};
    for (const [k, v] of Object.entries(act.args)) {
      if (!k.startsWith('_pos')) cleanArgs[k] = v;
    }
    try {
      const r = await fetch('/api/run', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({category: act.cat, command: act.cmd, args: cleanArgs}),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      btn.textContent = data.rc === 0 ? '✓ Done' : '✗ Failed';
      // Render output as <details>
      const det = document.createElement('details');
      const sum = document.createElement('summary');
      sum.textContent = data.rc === 0 ? 'Output' : `Error (rc=${data.rc})`;
      det.appendChild(sum);
      const pre = document.createElement('pre');
      pre.textContent = (data.stdout || '') + (data.stderr ? '\n--- stderr ---\n' + data.stderr : '');
      det.appendChild(pre);
      block.appendChild(det);
      if (data.rc === 0) toast('Ran ✓', 'success');
      else toast(`Failed (rc=${data.rc})`, 'error');
    } catch (e) {
      btn.textContent = '✗ Error';
      const det = document.createElement('details');
      det.open = true;
      const sum = document.createElement('summary');
      sum.textContent = 'Error';
      det.appendChild(sum);
      const pre = document.createElement('pre');
      pre.textContent = e.message;
      det.appendChild(pre);
      block.appendChild(det);
      toast(`Run failed: ${e.message}`, 'error');
    }
  }

  function scrollToBottom() {
    if (!A.messagesEl) return;
    requestAnimationFrame(() => {
      A.messagesEl.scrollTop = A.messagesEl.scrollHeight;
    });
  }

  function showTyping() {
    hideTyping();
    A.typingEl = document.createElement('div');
    A.typingEl.className = 'ai-typing';
    A.typingEl.innerHTML = '<span></span><span></span><span></span>';
    A.messagesEl.appendChild(A.typingEl);
    scrollToBottom();
  }

  function hideTyping() {
    if (A.typingEl) { A.typingEl.remove(); A.typingEl = null; }
  }

  // ----- Send -----------------------------------------------------------
  async function onSend() {
    if (A.sending) return;
    const text = (A.inputEl.value || '').trim();
    if (!text) return;
    A.inputEl.value = '';
    autoResize();
    A.sending = true;
    A.sendBtn.disabled = true;

    const userMsg = {role: 'user', content: text};
    A.history.push(userMsg);
    saveHistory();
    // Re-render to clear "empty" state, or just append
    if (A.messagesEl.querySelector('.ai-empty')) renderMessages();
    else renderMessage(userMsg);
    scrollToBottom();

    showTyping();

    try {
      const messages = A.history.map(m => ({role: m.role, content: m.content}));
      const r = await fetch('/api/ai/chat', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({messages}),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}: ${await r.text().catch(() => '')}`);
      const data = await r.json();
      const content = data.content || data.message?.content || data.response || '(no response)';
      hideTyping();
      const assistantMsg = {role: 'assistant', content};
      A.history.push(assistantMsg);
      saveHistory();
      renderMessage(assistantMsg);
      scrollToBottom();
    } catch (e) {
      hideTyping();
      const errMsg = {role: 'assistant', content: `⚠️ Error: ${e.message}`};
      A.history.push(errMsg);
      saveHistory();
      renderMessage(errMsg);
      scrollToBottom();
      toast(`AI error: ${e.message}`, 'error');
    } finally {
      A.sending = false;
      A.sendBtn.disabled = false;
      A.inputEl.focus();
    }
  }

  function clearChat() {
    if (!A.history.length) return;
    if (!window.confirm('Clear chat history?')) return;
    A.history = [];
    saveHistory();
    renderMessages();
  }

  // ----- Open / close / toggle ----------------------------------------
  function open() {
    if (!A.initialized) build();
    A.pane.classList.add('open');
    A.isOpen = true;
    setTimeout(() => A.inputEl?.focus(), 200);
  }

  function close() {
    if (!A.pane) return;
    A.pane.classList.remove('open');
    A.isOpen = false;
  }

  function toggle() {
    if (!A.initialized) { open(); return; }
    if (A.isOpen) close(); else open();
  }

  // Esc closes when focused inside pane
  window.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && A.isOpen) {
      if (document.activeElement === A.inputEl) {
        if (A.inputEl.value) return; // let Esc clear textarea? no — just close
      }
      close();
    }
  });

  window.tkAI = {open, close, toggle};
})();
