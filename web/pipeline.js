/* tk — Pipeline editor (pipeline.js)
   Node-graph UI module. Attaches to window.tkPipeline.
   Self-contained — relies on the global `state` from app.js for category list,
   and uses /api/schema/<cat>/<cmd>, /api/recipes(*), /api/jobs/<id>/events.
   ------------------------------------------------------------------ */
(function () {
  'use strict';

  // ----- Module state ---------------------------------------------------
  const M = {
    initialized: false,
    open: false,
    page: null,           // root .pl-page element
    canvas: null,         // .pl-canvas
    canvasInner: null,    // .pl-canvas-inner
    svg: null,            // svg layer for edges
    palette: null,        // .pl-palette
    nodes: new Map(),     // id -> node object
    edges: [],            // [{from, to}]
    schemaCache: new Map(), // 'cat:cmd' -> {args: [...]}
    nodeCounter: 0,
    // Drag state
    draggingNode: null,
    dragOffsetX: 0,
    dragOffsetY: 0,
    // Port wiring state
    wiringFrom: null,     // {nodeId, x, y}
    tempEdge: null,       // SVG path while dragging
    // Run state
    running: false,
    currentJobId: null,
    currentES: null,
  };

  // ----- Small helpers --------------------------------------------------
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g,
    c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));

  function toast(msg, kind = 'info') {
    // Reuse the existing toast container
    const box = document.getElementById('toasts');
    if (!box) { console.log('[pipeline]', kind, msg); return; }
    const t = document.createElement('div');
    t.className = `toast ${kind}`;
    t.textContent = msg;
    box.appendChild(t);
    setTimeout(() => t.remove(), 3200);
  }

  function nodeId() {
    M.nodeCounter += 1;
    return 'n' + M.nodeCounter;
  }

  async function fetchSchema(cat, cmd) {
    const key = `${cat}:${cmd}`;
    if (M.schemaCache.has(key)) return M.schemaCache.get(key);
    try {
      const r = await fetch(`/api/schema/${cat}/${encodeURIComponent(cmd)}`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      M.schemaCache.set(key, data);
      return data;
    } catch (e) {
      console.warn('schema fetch failed', cat, cmd, e);
      return {args: []};
    }
  }

  // ----- Build the page on first open -----------------------------------
  function buildPage() {
    const root = document.getElementById('pipeline-page');
    if (!root) return;
    root.className = 'pl-page';
    root.innerHTML = `
      <div class="pl-header">
        <h2>🧬 Pipeline editor</h2>
        <button type="button" class="pl-run-btn" id="pl-run">▶ Run pipeline</button>
        <button type="button" id="pl-save">💾 Save as recipe</button>
        <select id="pl-load"><option value="">📂 Load recipe…</option></select>
        <button type="button" id="pl-clear">🗑 Clear</button>
        <div class="pl-spacer"></div>
        <button type="button" id="pl-close">✕ Close</button>
      </div>
      <div class="pl-body">
        <aside class="pl-palette">
          <input type="text" class="pl-palette-filter" id="pl-palette-filter" placeholder="Filter tools…">
          <div id="pl-palette-list"></div>
        </aside>
        <div class="pl-canvas" id="pl-canvas">
          <div class="pl-canvas-inner" id="pl-canvas-inner">
            <svg class="pl-svg" id="pl-svg" xmlns="http://www.w3.org/2000/svg"></svg>
            <div class="pl-empty" id="pl-empty">
              <div class="pl-empty-icon">🧬</div>
              <div>Drag tools from the left to begin.</div>
              <div class="small" style="opacity:.7; margin-top:6px;">Connect output → input to chain.</div>
            </div>
          </div>
        </div>
      </div>
    `;

    M.page = root;
    M.canvas = root.querySelector('#pl-canvas');
    M.canvasInner = root.querySelector('#pl-canvas-inner');
    M.svg = root.querySelector('#pl-svg');
    M.palette = root.querySelector('#pl-palette-list');

    root.querySelector('#pl-close').addEventListener('click', close);
    root.querySelector('#pl-clear').addEventListener('click', clearCanvas);
    root.querySelector('#pl-run').addEventListener('click', runPipeline);
    root.querySelector('#pl-save').addEventListener('click', saveRecipePrompt);
    root.querySelector('#pl-load').addEventListener('change', onLoadSelected);
    root.querySelector('#pl-palette-filter').addEventListener('input', renderPalette);

    // Global mouse events for wiring / dragging
    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mouseup', onMouseUp);
    window.addEventListener('keydown', onKey);

    M.initialized = true;
  }

  // ----- Palette --------------------------------------------------------
  function renderPalette() {
    if (!M.palette) return;
    const filter = (document.getElementById('pl-palette-filter')?.value || '').toLowerCase().trim();
    const cats = (window.state && window.state.categories) || [];
    M.palette.innerHTML = '';
    if (!cats.length) {
      M.palette.innerHTML = '<div class="muted small" style="padding:8px;">No categories loaded.</div>';
      return;
    }
    for (const c of cats) {
      const matching = (c.commands || []).filter(cmd => {
        if (!filter) return true;
        return (`${c.key}:${cmd.name}`).toLowerCase().includes(filter)
          || (cmd.help || '').toLowerCase().includes(filter);
      });
      if (!matching.length) continue;
      const h = document.createElement('h3');
      h.textContent = `${c.icon || ''} ${c.label || c.key}`;
      M.palette.appendChild(h);
      for (const cmd of matching) {
        const item = document.createElement('div');
        item.className = 'pl-tool';
        item.draggable = true;
        item.dataset.cat = c.key;
        item.dataset.cmd = cmd.name;
        item.title = cmd.help || '';
        item.innerHTML = `
          <span class="pl-tool-icon">${c.icon || '•'}</span>
          <span class="pl-tool-name">${esc(c.key)}:${esc(cmd.name)}</span>
        `;
        item.addEventListener('dragstart', (e) => {
          e.dataTransfer.setData('text/plain', `${c.key}:${cmd.name}`);
          e.dataTransfer.effectAllowed = 'copy';
        });
        item.addEventListener('click', () => {
          // Click also adds to center of viewport
          const rect = M.canvas.getBoundingClientRect();
          const x = M.canvas.scrollLeft + rect.width / 2 - 120;
          const y = M.canvas.scrollTop + rect.height / 2 - 60;
          addNode(c.key, cmd.name, x, y);
        });
        M.palette.appendChild(item);
      }
    }
  }

  // ----- Canvas drop ----------------------------------------------------
  function wireCanvasDrop() {
    M.canvas.addEventListener('dragover', (e) => {
      e.preventDefault();
      e.dataTransfer.dropEffect = 'copy';
    });
    M.canvas.addEventListener('drop', (e) => {
      e.preventDefault();
      const data = e.dataTransfer.getData('text/plain');
      if (!data || !data.includes(':')) return;
      const [cat, cmd] = data.split(':');
      const rect = M.canvas.getBoundingClientRect();
      const x = M.canvas.scrollLeft + (e.clientX - rect.left) - 60;
      const y = M.canvas.scrollTop + (e.clientY - rect.top) - 20;
      addNode(cat, cmd, x, y);
    });
  }

  // ----- Node ops -------------------------------------------------------
  async function addNode(cat, cmd, x, y, opts = {}) {
    const id = opts.id || nodeId();
    const node = {
      id,
      cat,
      cmd,
      x: Math.max(0, x),
      y: Math.max(0, y),
      args: opts.args || {},
      state: 'idle',
      el: null,
      schema: null,
    };
    M.nodes.set(id, node);
    renderNode(node);
    updateEmpty();
    // Load schema and populate body
    node.schema = await fetchSchema(cat, cmd);
    populateNodeBody(node);
    // Restore args from opts if any
    if (opts.args) applyNodeArgs(node, opts.args);
    redrawEdges();
    return node;
  }

  function renderNode(node) {
    const el = document.createElement('div');
    el.className = 'pl-node';
    el.dataset.state = node.state;
    el.dataset.id = node.id;
    el.style.left = node.x + 'px';
    el.style.top = node.y + 'px';
    const cat = (window.state?.categories || []).find(c => c.key === node.cat);
    const icon = cat?.icon || '•';
    el.innerHTML = `
      <div class="pl-port in" data-port="in"></div>
      <div class="pl-node-header">
        <span class="pl-node-icon">${icon}</span>
        <span class="pl-node-title">${esc(node.cat)}:${esc(node.cmd)}</span>
        <span class="pl-node-state">idle</span>
        <button type="button" class="pl-node-del" title="Remove">✕</button>
      </div>
      <div class="pl-node-body"><div class="pl-no-args">Loading…</div></div>
      <div class="pl-port out" data-port="out"></div>
    `;
    el.querySelector('.pl-node-header').addEventListener('mousedown', (e) => onNodeMouseDown(e, node));
    el.querySelector('.pl-node-del').addEventListener('click', (e) => {
      e.stopPropagation();
      removeNode(node.id);
    });
    el.querySelector('.pl-port.in').addEventListener('mousedown', (e) => onPortMouseDown(e, node, 'in'));
    el.querySelector('.pl-port.out').addEventListener('mousedown', (e) => onPortMouseDown(e, node, 'out'));
    el.querySelector('.pl-port.in').addEventListener('mouseup', (e) => onPortMouseUp(e, node, 'in'));
    el.querySelector('.pl-port.out').addEventListener('mouseup', (e) => onPortMouseUp(e, node, 'out'));

    M.canvasInner.appendChild(el);
    node.el = el;
  }

  function populateNodeBody(node) {
    const body = node.el.querySelector('.pl-node-body');
    body.innerHTML = '';
    const args = (node.schema?.args || []).filter(a => a.name !== 'cmd');
    if (!args.length) {
      const d = document.createElement('div');
      d.className = 'pl-no-args';
      d.textContent = '(no arguments)';
      body.appendChild(d);
      return;
    }
    for (const a of args) {
      const f = document.createElement('div');
      f.className = 'pl-field';
      const label = a.positional ? a.name : (a.flags?.[0] || a.name);

      if (a.type === 'bool') {
        f.classList.add('pl-field-checkbox');
        const cb = document.createElement('input');
        cb.type = 'checkbox';
        cb.dataset.argname = a.name;
        cb.dataset.argtype = 'bool';
        cb.checked = !!(node.args[a.name] ?? a.default);
        cb.addEventListener('change', () => { node.args[a.name] = cb.checked; });
        const lbl = document.createElement('label');
        lbl.textContent = label;
        lbl.style.cursor = 'pointer';
        f.appendChild(cb);
        f.appendChild(lbl);
        body.appendChild(f);
        continue;
      }

      const lbl = document.createElement('label');
      lbl.textContent = label + (a.required ? ' *' : '');
      lbl.title = a.help || '';
      f.appendChild(lbl);

      let inp;
      if (a.choices && a.choices.length) {
        inp = document.createElement('select');
        if (!a.required) {
          const o = document.createElement('option');
          o.value = ''; o.textContent = '(default)';
          inp.appendChild(o);
        }
        for (const c of a.choices) {
          const o = document.createElement('option');
          o.value = c; o.textContent = c;
          if ((node.args[a.name] ?? a.default) === c) o.selected = true;
          inp.appendChild(o);
        }
      } else {
        inp = document.createElement('input');
        inp.type = (a.type === 'int' || a.type === 'float') ? 'number' : 'text';
        if (a.type === 'float') inp.step = 'any';
        const cur = node.args[a.name];
        if (cur != null) inp.value = cur;
        if (a.default != null && a.default !== false && a.default !== '') {
          inp.placeholder = String(a.default);
        } else if (a.likely_file) {
          // Hint at piping from prior node
          const hasParent = M.edges.some(e => e.to === node.id);
          inp.placeholder = hasParent ? '{{prev.output}}' : 'filename';
        }
      }
      inp.dataset.argname = a.name;
      inp.dataset.argtype = a.type || 'str';
      if (a.positional) inp.dataset.positional = '1';
      if (a.flags) inp.dataset.flag = a.flags[0];
      if (a.likely_file) inp.dataset.file = '1';
      inp.addEventListener('input', () => {
        node.args[a.name] = inp.value;
        markPipedFields(node);
      });
      inp.addEventListener('change', () => { node.args[a.name] = inp.value; });
      f.appendChild(inp);
      body.appendChild(f);
    }
    markPipedFields(node);
  }

  function applyNodeArgs(node, args) {
    if (!node.el) return;
    for (const inp of node.el.querySelectorAll('[data-argname]')) {
      const k = inp.dataset.argname;
      if (!(k in args)) continue;
      if (inp.type === 'checkbox') inp.checked = !!args[k];
      else inp.value = args[k] ?? '';
    }
  }

  function markPipedFields(node) {
    if (!node.el) return;
    const hasParent = M.edges.some(e => e.to === node.id);
    for (const inp of node.el.querySelectorAll('input[data-file="1"]')) {
      const v = (inp.value || '').trim();
      if (hasParent && (v === '' || v === '{{prev.output}}')) {
        inp.classList.add('pl-piped');
        if (v === '') inp.placeholder = '{{prev.output}}';
      } else {
        inp.classList.remove('pl-piped');
      }
    }
  }

  function removeNode(id) {
    const node = M.nodes.get(id);
    if (!node) return;
    node.el?.remove();
    M.nodes.delete(id);
    M.edges = M.edges.filter(e => e.from !== id && e.to !== id);
    redrawEdges();
    updateEmpty();
    for (const n of M.nodes.values()) markPipedFields(n);
  }

  function updateEmpty() {
    const empty = document.getElementById('pl-empty');
    if (!empty) return;
    empty.style.display = M.nodes.size === 0 ? '' : 'none';
  }

  // ----- Node dragging --------------------------------------------------
  function onNodeMouseDown(e, node) {
    if (e.button !== 0) return;
    e.preventDefault();
    M.draggingNode = node;
    const rect = node.el.getBoundingClientRect();
    M.dragOffsetX = e.clientX - rect.left;
    M.dragOffsetY = e.clientY - rect.top;
    node.el.style.cursor = 'grabbing';
  }

  function onMouseMove(e) {
    if (M.draggingNode) {
      const canvasRect = M.canvas.getBoundingClientRect();
      const x = (e.clientX - canvasRect.left + M.canvas.scrollLeft) - M.dragOffsetX;
      const y = (e.clientY - canvasRect.top + M.canvas.scrollTop) - M.dragOffsetY;
      M.draggingNode.x = Math.max(0, x);
      M.draggingNode.y = Math.max(0, y);
      M.draggingNode.el.style.left = M.draggingNode.x + 'px';
      M.draggingNode.el.style.top = M.draggingNode.y + 'px';
      redrawEdges();
    }
    if (M.wiringFrom) {
      const pt = getCanvasPoint(e);
      drawTempEdge(M.wiringFrom.x, M.wiringFrom.y, pt.x, pt.y);
    }
  }

  function onMouseUp(e) {
    if (M.draggingNode) {
      M.draggingNode.el.style.cursor = '';
      M.draggingNode = null;
    }
    if (M.wiringFrom) {
      // Cancel wiring if mouseup not over a port (port handler runs first)
      setTimeout(() => {
        if (M.wiringFrom) {
          cancelWiring();
        }
      }, 0);
    }
  }

  function onKey(e) {
    if (!M.open) return;
    if (e.key === 'Escape') {
      if (M.wiringFrom) { cancelWiring(); return; }
      close();
    }
  }

  // ----- Port wiring ----------------------------------------------------
  function onPortMouseDown(e, node, side) {
    if (e.button !== 0) return;
    e.preventDefault();
    e.stopPropagation();
    if (side !== 'out') return; // only drag from outputs
    const p = portPoint(node, 'out');
    M.wiringFrom = {nodeId: node.id, x: p.x, y: p.y};
  }

  function onPortMouseUp(e, node, side) {
    if (!M.wiringFrom) return;
    e.preventDefault();
    e.stopPropagation();
    if (side === 'in' && node.id !== M.wiringFrom.nodeId) {
      // Prevent cycles (simple check): if there's a path from node to wiringFrom, refuse
      if (!createsCycle(M.wiringFrom.nodeId, node.id)) {
        // Avoid duplicates
        if (!M.edges.some(ed => ed.from === M.wiringFrom.nodeId && ed.to === node.id)) {
          M.edges.push({from: M.wiringFrom.nodeId, to: node.id});
        }
      } else {
        toast('Cycle prevented', 'error');
      }
    }
    cancelWiring();
    redrawEdges();
    for (const n of M.nodes.values()) markPipedFields(n);
  }

  function cancelWiring() {
    M.wiringFrom = null;
    if (M.tempEdge) { M.tempEdge.remove(); M.tempEdge = null; }
  }

  function createsCycle(fromId, toId) {
    // Does adding from->to create a cycle? i.e. is there a path from toId back to fromId?
    const visited = new Set();
    const stack = [toId];
    while (stack.length) {
      const cur = stack.pop();
      if (cur === fromId) return true;
      if (visited.has(cur)) continue;
      visited.add(cur);
      for (const e of M.edges) {
        if (e.from === cur) stack.push(e.to);
      }
    }
    return false;
  }

  // ----- SVG edges ------------------------------------------------------
  function portPoint(node, side) {
    // Position is relative to canvasInner
    const w = node.el.offsetWidth || 240;
    const h = node.el.offsetHeight || 100;
    if (side === 'out') return {x: node.x + w / 2, y: node.y + h};
    return {x: node.x + w / 2, y: node.y};
  }

  function getCanvasPoint(e) {
    const rect = M.canvasInner.getBoundingClientRect();
    return {x: e.clientX - rect.left, y: e.clientY - rect.top};
  }

  function bezierPath(x1, y1, x2, y2) {
    const dy = Math.max(40, Math.abs(y2 - y1) * 0.5);
    return `M ${x1} ${y1} C ${x1} ${y1 + dy}, ${x2} ${y2 - dy}, ${x2} ${y2}`;
  }

  function redrawEdges() {
    if (!M.svg) return;
    // Make sure svg covers the canvas-inner
    M.svg.setAttribute('width', M.canvasInner.offsetWidth);
    M.svg.setAttribute('height', M.canvasInner.offsetHeight);
    // Clear existing edges (but keep temp edge if any)
    const existing = M.svg.querySelectorAll('.pl-edge');
    existing.forEach(e => e.remove());
    for (const edge of M.edges) {
      const a = M.nodes.get(edge.from);
      const b = M.nodes.get(edge.to);
      if (!a || !b) continue;
      const p1 = portPoint(a, 'out');
      const p2 = portPoint(b, 'in');
      const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      path.setAttribute('d', bezierPath(p1.x, p1.y, p2.x, p2.y));
      path.setAttribute('class', 'pl-edge' + (a.state === 'running' ? ' pl-edge-running' : ''));
      path.dataset.from = edge.from;
      path.dataset.to = edge.to;
      path.addEventListener('click', () => {
        M.edges = M.edges.filter(e => !(e.from === edge.from && e.to === edge.to));
        redrawEdges();
        for (const n of M.nodes.values()) markPipedFields(n);
      });
      M.svg.appendChild(path);
    }
  }

  function drawTempEdge(x1, y1, x2, y2) {
    if (!M.tempEdge) {
      M.tempEdge = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      M.tempEdge.setAttribute('class', 'pl-edge pl-edge-temp');
      M.svg.appendChild(M.tempEdge);
    }
    M.tempEdge.setAttribute('d', bezierPath(x1, y1, x2, y2));
  }

  // ----- Topo sort & recipe building -----------------------------------
  function topoSort() {
    const indeg = new Map();
    for (const id of M.nodes.keys()) indeg.set(id, 0);
    for (const e of M.edges) indeg.set(e.to, (indeg.get(e.to) || 0) + 1);
    const queue = [];
    for (const [id, d] of indeg.entries()) if (d === 0) queue.push(id);
    const out = [];
    while (queue.length) {
      const cur = queue.shift();
      out.push(cur);
      for (const e of M.edges) if (e.from === cur) {
        const d = indeg.get(e.to) - 1;
        indeg.set(e.to, d);
        if (d === 0) queue.push(e.to);
      }
    }
    if (out.length !== M.nodes.size) return null; // cycle
    return out;
  }

  function buildRecipe(name = '_inline') {
    const sortedIds = topoSort();
    if (!sortedIds) return null;
    const steps = sortedIds.map(id => {
      const n = M.nodes.get(id);
      const depends = M.edges.filter(e => e.to === id).map(e => e.from);
      return {
        id,
        tool: `${n.cat}:${n.cmd}`,
        args: {...n.args},
        depends,
        pos: {x: n.x, y: n.y},
      };
    });
    return {name, steps};
  }

  // ----- Run pipeline ---------------------------------------------------
  async function runPipeline() {
    if (M.running) { toast('Already running', 'info'); return; }
    if (M.nodes.size === 0) { toast('Add at least one tool', 'info'); return; }
    const recipe = buildRecipe('_inline');
    if (!recipe) { toast('Cycle detected — fix the graph', 'error'); return; }
    // Reset node states
    for (const n of M.nodes.values()) setNodeState(n, 'queued', '');
    redrawEdges();
    M.running = true;
    const runBtn = document.getElementById('pl-run');
    if (runBtn) { runBtn.disabled = true; runBtn.textContent = '⏳ Running…'; }
    let jobId;
    try {
      const r = await fetch('/api/recipes/run', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({recipe}),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}: ${await r.text()}`);
      const data = await r.json();
      jobId = data.job_id;
      if (!jobId) throw new Error('No job_id returned');
    } catch (e) {
      toast(`Run failed: ${e.message}`, 'error');
      M.running = false;
      if (runBtn) { runBtn.disabled = false; runBtn.textContent = '▶ Run pipeline'; }
      for (const n of M.nodes.values()) if (n.state === 'queued') setNodeState(n, 'idle', '');
      return;
    }
    M.currentJobId = jobId;
    streamJobEvents(jobId);
  }

  function streamJobEvents(jobId) {
    let es;
    try {
      es = new EventSource(`/api/jobs/${jobId}/events`);
    } catch (e) {
      toast(`SSE error: ${e.message}`, 'error');
      finishRun();
      return;
    }
    M.currentES = es;
    const onNodeStart = (e) => {
      try {
        const data = JSON.parse(e.data);
        const n = M.nodes.get(data.node_id);
        if (n) { setNodeState(n, 'running', ''); redrawEdges(); }
      } catch (_) {}
    };
    const onNodeDone = (e) => {
      try {
        const data = JSON.parse(e.data);
        const n = M.nodes.get(data.node_id);
        if (n) { setNodeState(n, 'done', ''); redrawEdges(); }
      } catch (_) {}
    };
    const onNodeError = (e) => {
      try {
        const data = JSON.parse(e.data);
        const n = M.nodes.get(data.node_id);
        if (n) { setNodeState(n, 'error', data.error || data.message || ''); redrawEdges(); }
      } catch (_) {}
    };
    es.addEventListener('node_start', onNodeStart);
    es.addEventListener('node_done', onNodeDone);
    es.addEventListener('node_error', onNodeError);
    es.addEventListener('done', (e) => {
      try {
        const data = JSON.parse(e.data || '{}');
        const failed = (data.failed != null) ? data.failed : 0;
        if (failed > 0) toast(`Pipeline finished with ${failed} error(s)`, 'error');
        else toast('Pipeline finished ✓', 'success');
      } catch (_) {
        toast('Pipeline finished', 'success');
      }
      es.close();
      finishRun();
    });
    es.onerror = () => {
      try { es.close(); } catch (_) {}
      finishRun();
    };
  }

  function finishRun() {
    M.running = false;
    M.currentJobId = null;
    M.currentES = null;
    const runBtn = document.getElementById('pl-run');
    if (runBtn) { runBtn.disabled = false; runBtn.textContent = '▶ Run pipeline'; }
  }

  function setNodeState(node, state, errMsg) {
    node.state = state;
    if (!node.el) return;
    node.el.dataset.state = state;
    const lbl = node.el.querySelector('.pl-node-state');
    if (lbl) lbl.textContent = state;
    const body = node.el.querySelector('.pl-node-body');
    if (body) {
      const existing = body.querySelector('.pl-err');
      if (existing) existing.remove();
      if (state === 'error' && errMsg) {
        const d = document.createElement('div');
        d.className = 'pl-err';
        d.textContent = errMsg;
        body.appendChild(d);
      }
    }
  }

  // ----- Recipes (save / load) -----------------------------------------
  async function saveRecipePrompt() {
    if (M.nodes.size === 0) { toast('Nothing to save', 'info'); return; }
    const name = window.prompt('Recipe name:');
    if (!name) return;
    const recipe = buildRecipe(name);
    if (!recipe) { toast('Cycle detected — cannot save', 'error'); return; }
    try {
      const r = await fetch('/api/recipes', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({name, recipe}),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      toast(`Recipe "${name}" saved ✓`, 'success');
      await refreshRecipeList();
    } catch (e) {
      toast(`Save failed: ${e.message}`, 'error');
    }
  }

  async function refreshRecipeList() {
    const sel = document.getElementById('pl-load');
    if (!sel) return;
    try {
      const r = await fetch('/api/recipes');
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      const list = data.recipes || data || [];
      sel.innerHTML = '<option value="">📂 Load recipe…</option>';
      for (const item of list) {
        const name = typeof item === 'string' ? item : (item.name || '');
        if (!name) continue;
        const o = document.createElement('option');
        o.value = name;
        o.textContent = name;
        sel.appendChild(o);
      }
    } catch (e) {
      // Endpoint not yet available — silent
    }
  }

  async function onLoadSelected(e) {
    const name = e.target.value;
    if (!name) return;
    try {
      const r = await fetch(`/api/recipes/${encodeURIComponent(name)}`);
      let recipe;
      if (r.ok) {
        const data = await r.json();
        recipe = data.recipe || data;
      } else {
        // Fallback: GET full list and find by name
        const r2 = await fetch('/api/recipes');
        const list = (await r2.json()).recipes || [];
        recipe = list.find(x => x.name === name) || list.find(x => x.name === name)?.recipe;
      }
      if (!recipe || !recipe.steps) throw new Error('Recipe not found');
      await loadRecipeIntoCanvas(recipe);
      toast(`Loaded "${name}"`, 'success');
    } catch (err) {
      toast(`Load failed: ${err.message}`, 'error');
    } finally {
      e.target.value = '';
    }
  }

  async function loadRecipeIntoCanvas(recipe) {
    clearCanvas();
    // Map old id -> new id
    const idMap = new Map();
    let i = 0;
    for (const step of recipe.steps || []) {
      const [cat, cmd] = (step.tool || '').split(':');
      if (!cat || !cmd) continue;
      const x = step.pos?.x ?? (60 + (i % 4) * 280);
      const y = step.pos?.y ?? (60 + Math.floor(i / 4) * 220);
      const node = await addNode(cat, cmd, x, y, {args: step.args || {}});
      idMap.set(step.id, node.id);
      i++;
    }
    // Edges
    for (const step of recipe.steps || []) {
      for (const dep of step.depends || []) {
        const from = idMap.get(dep);
        const to = idMap.get(step.id);
        if (from && to) M.edges.push({from, to});
      }
    }
    redrawEdges();
    for (const n of M.nodes.values()) markPipedFields(n);
  }

  // ----- Clear ----------------------------------------------------------
  function clearCanvas() {
    for (const n of M.nodes.values()) n.el?.remove();
    M.nodes.clear();
    M.edges = [];
    redrawEdges();
    updateEmpty();
  }

  // ----- Open / close --------------------------------------------------
  function open() {
    const root = document.getElementById('pipeline-page');
    if (!root) return;
    if (!M.initialized) {
      buildPage();
      wireCanvasDrop();
    }
    root.classList.remove('hidden');
    M.open = true;
    renderPalette();
    refreshRecipeList();
    redrawEdges();
  }

  function close() {
    const root = document.getElementById('pipeline-page');
    if (!root) return;
    root.classList.add('hidden');
    M.open = false;
    if (M.currentES) { try { M.currentES.close(); } catch (_) {} }
  }

  // Expose
  window.tkPipeline = {open, close};
})();
