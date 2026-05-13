/* tk — Personal Toolkit  (app.js)
   Interactive web client.
   ------------------------------------------------------------------ */

const state = {
  categories: [],
  flatCommands: [],
  currentCategory: null,
  currentCommand: null,
  workspaceFiles: [],
  fieldRefs: [],
  paletteIndex: 0,
  paletteResults: [],
  cmdListIndex: -1,
  isRunning: false,
  runStart: 0,
  runTimer: null,
  lastResult: null,
};

/* --------------------------------- API ---------------------------------- */
const api = {
  async getCategories() {
    const r = await fetch('/api/categories');
    return r.json();
  },
  async getSchema(category, command) {
    const r = await fetch(`/api/schema/${category}/${encodeURIComponent(command)}`);
    return r.json();
  },
  async run(category, command, args) {
    const r = await fetch('/api/run', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({category, command, args}),
    });
    return r.json();
  },
  async upload(files) {
    const fd = new FormData();
    for (const f of files) fd.append('files', f);
    const r = await fetch('/api/upload', {method: 'POST', body: fd});
    return r.json();
  },
  async listFiles() {
    const r = await fetch('/api/files');
    return r.json();
  },
  async deleteFile(name) {
    const r = await fetch(`/api/files/${encodeURIComponent(name)}`, {method: 'DELETE'});
    return r.json();
  },
  async clearWorkspace() {
    const r = await fetch('/api/clear', {method: 'DELETE'});
    return r.json();
  },
};

/* --------------------------------- Storage ------------------------------ */
const storage = {
  getRecent() {
    try { return JSON.parse(localStorage.getItem('tk-recent') || '[]'); }
    catch { return []; }
  },
  addRecent(category, command) {
    const recent = this.getRecent();
    const key = `${category}/${command}`;
    const filtered = recent.filter(r => `${r.category}/${r.command}` !== key);
    filtered.unshift({category, command, ts: Date.now()});
    localStorage.setItem('tk-recent', JSON.stringify(filtered.slice(0, 12)));
  },
  clearRecent() {
    localStorage.removeItem('tk-recent');
  },
  getFavorites() {
    try { return JSON.parse(localStorage.getItem('tk-favs') || '[]'); }
    catch { return []; }
  },
  toggleFavorite(category, command) {
    const favs = this.getFavorites();
    const idx = favs.findIndex(f => f.category === category && f.command === command);
    if (idx >= 0) { favs.splice(idx, 1); }
    else { favs.push({category, command}); }
    localStorage.setItem('tk-favs', JSON.stringify(favs));
    return idx < 0;
  },
  isFavorite(category, command) {
    return this.getFavorites().some(f => f.category === category && f.command === command);
  },
  getHistory() {
    try { return JSON.parse(localStorage.getItem('tk-history') || '[]'); }
    catch { return []; }
  },
  addHistory(entry) {
    const h = this.getHistory();
    h.unshift({...entry, ts: Date.now()});
    localStorage.setItem('tk-history', JSON.stringify(h.slice(0, 30)));
  },
  clearHistory() {
    localStorage.removeItem('tk-history');
  },
  getPresets(category, command) {
    try { return JSON.parse(localStorage.getItem(`tk-preset-${category}/${command}`) || '[]'); }
    catch { return []; }
  },
  savePreset(category, command, name, values) {
    const list = this.getPresets(category, command);
    const i = list.findIndex(p => p.name === name);
    const entry = {name, values, ts: Date.now()};
    if (i >= 0) list[i] = entry;
    else list.push(entry);
    localStorage.setItem(`tk-preset-${category}/${command}`, JSON.stringify(list));
  },
  deletePreset(category, command, name) {
    const list = this.getPresets(category, command).filter(p => p.name !== name);
    localStorage.setItem(`tk-preset-${category}/${command}`, JSON.stringify(list));
  },
  tourSeen() { return localStorage.getItem('tk-tour-seen') === '1'; },
  markTourSeen() { localStorage.setItem('tk-tour-seen', '1'); },
};

/* --------------------------------- Built-in samples --------------------- */
// Per command, optional pre-fill values (or workspace files we'll create on demand).
const SAMPLES = {
  'text/b64encode':    {text: 'hello world'},
  'text/b64decode':    {text: 'aGVsbG8gd29ybGQ='},
  'text/hash':         {text: 'hello world', algo: 'sha256'},
  'text/snake':        {text: 'HelloWorldExample'},
  'text/kebab':        {text: 'HelloWorldExample'},
  'text/camel':        {text: 'hello world example'},
  'text/pascal':       {text: 'hello world example'},
  'text/json-format':  {text: '{"name":"alice","age":30,"hobbies":["go","pdfs"]}'},
  'text/json-minify':  {text: '{\n  "x": 1,\n  "y": 2\n}'},
  'text/rot13':        {text: 'Hello, World!'},
  'text/normalize':    {text: 'Café — naïve résumé', form: 'NFKD'},
  'text/md-to-html':   {text: '# Hello\n\n**bold** and *italic* and `code`.\n\n- item 1\n- item 2'},
  'crypto/password':   {length: '24', count: '3', '--symbols': true},
  'crypto/uuid':       {count: '5'},
  'crypto/totp':       {secret: 'JBSWY3DPEHPK3PXP'},
  'crypto/caesar':     {text: 'Hello, World!', shift: '3'},
  'crypto/otpauth':    {secret: 'JBSWY3DPEHPK3PXP', account: 'alice@example.com', issuer: 'tk'},
  'crypto/random':     {bytes: '16', format: 'hex'},
  'dev/regex':         {pattern: '(\\w+)@(\\w+)', text: 'alice@gmail bob@yahoo carol@example'},
  'dev/regex-explain': {pattern: '^(\\d{3})-(\\d{4})$'},
  'dev/calc':          {expression: 'sin(pi/4)*sqrt(2)'},
  'dev/lorem':         {count: '2', unit: 'paragraphs'},
  'dev/base':          {number: 'ff', '--from-base': '16', '--to-base': '2'},
  'dev/timestamp':     {value: '1700000000'},
  'dev/slug':          {text: 'Hello, World!! 2026 — best ever'},
  'dev/color':         {color: '#3a7bd5'},
  'dev/cidr':          {cidr: '192.168.1.0/24'},
  'dev/ulid':          {count: '5'},
  'dev/semver-bump':   {version: '1.2.3', bump: 'minor'},
  'dev/mock':          {count: '5', format: 'table'},
  'net/dns':           {host: 'github.com'},
  'net/http':          {url: 'https://httpbin.org/json', method: 'GET'},
  'net/url-parse':     {url: 'https://user:pw@host.example.com:8443/path/to?a=1&b=2#frag'},
  'net/url-build':     {base: 'https://api.example.com', path: '/v1/items', '--params': ['q=tools', 'limit=10']},
  'net/ssl-info':      {host: 'github.com', port: '443'},
  'net/check':         {url: 'https://github.com'},
  'net/my-ip':         {},
  'qr/gen':            {text: 'https://anthropic.com'},
  'qr/wifi':           {ssid: 'MyHomeWiFi', '--password': 'supersecret123', security: 'WPA'},
  'qr/vcard':          {name: 'Alice Example', '--email': 'alice@example.com', '--phone': '+1-555-0100', '--org': 'Acme'},
  'data/jsonpath':     {path: '$.users[*].name'},
  'fs/sysinfo':        {},
  'fs/tree':           {dir: '.', '--depth': '2'},
  'fs/disk':           {dir: '.'},
  'oled/displays':     {},
  'convert/list':      {},
  'archive/zip-list':  {},
};

function getSample(category, command) {
  return SAMPLES[`${category}/${command}`];
}

/* --------------------------------- Toast -------------------------------- */
function toast(msg, kind = 'info') {
  const t = document.createElement('div');
  t.className = `toast ${kind}`;
  t.textContent = msg;
  document.getElementById('toasts').appendChild(t);
  setTimeout(() => t.remove(), 3200);
}

/* --------------------------------- Theme -------------------------------- */
function initTheme() {
  const saved = localStorage.getItem('tk-theme') || 'dark';
  document.documentElement.dataset.theme = saved;
  document.getElementById('theme-toggle').textContent = saved === 'dark' ? '☀️' : '🌙';
}
function toggleTheme() {
  const cur = document.documentElement.dataset.theme || 'dark';
  const next = cur === 'dark' ? 'light' : 'dark';
  document.documentElement.dataset.theme = next;
  localStorage.setItem('tk-theme', next);
  document.getElementById('theme-toggle').textContent = next === 'dark' ? '☀️' : '🌙';
}
document.getElementById('theme-toggle').addEventListener('click', toggleTheme);

/* --------------------------------- View routing ------------------------- */
function showView(name) {
  for (const id of ['welcome', 'commands', 'form']) {
    const el = document.getElementById(id);
    if (el) el.classList.toggle('hidden', id !== name);
  }
}

function goHome() {
  showView('welcome');
  document.querySelectorAll('#categories li').forEach(li => li.classList.remove('active'));
  state.currentCategory = null;
  state.currentCommand = null;
  setHash('');
  renderRecent();
  renderFavorites();
}

/* --------------------------------- URL routing -------------------------- */
let suppressHashEvent = false;
function setHash(h) {
  const target = h ? `#${h}` : '#';
  if (location.hash === target) return;
  suppressHashEvent = true;
  if (h) history.pushState(null, '', target);
  else history.pushState(null, '', location.pathname);
  setTimeout(() => suppressHashEvent = false, 50);
}
function applyHash() {
  const raw = location.hash.replace(/^#/, '');
  if (!raw) {
    showView('welcome');
    document.querySelectorAll('#categories li').forEach(li => li.classList.remove('active'));
    return;
  }
  const [cat, cmd] = raw.split('/');
  if (cmd) {
    const found = findCmd(cat, cmd);
    if (found) {
      _selectCategoryNoHash(cat);
      _selectCommandNoHash(cat, found.cmd);
    }
  } else {
    _selectCategoryNoHash(cat);
  }
}
window.addEventListener('hashchange', () => {
  if (suppressHashEvent) return;
  applyHash();
});

/* --------------------------------- Breadcrumbs -------------------------- */
function renderBreadcrumbs() {
  const el = document.getElementById('breadcrumbs');
  if (!el) return;
  if (!state.currentCategory) { el.innerHTML = ''; return; }
  const cat = state.categories.find(c => c.key === state.currentCategory);
  const parts = [
    `<a data-bc="home">tk</a>`,
    `<span class="sep">/</span>`,
    `<a data-bc="cat">${escapeHTML(cat ? cat.label : state.currentCategory)}</a>`,
  ];
  if (state.currentCommand) {
    parts.push(`<span class="sep">/</span>`,
               `<span class="current">${escapeHTML(state.currentCommand)}</span>`);
  }
  el.innerHTML = parts.join(' ');
  el.querySelector('[data-bc="home"]').addEventListener('click', goHome);
  const catLink = el.querySelector('[data-bc="cat"]');
  if (catLink) catLink.addEventListener('click', () => selectCategory(state.currentCategory));
}

/* --------------------------------- Categories load ---------------------- */
async function loadCategories() {
  const data = await api.getCategories();
  state.categories = data.categories || [];
  state.flatCommands = state.categories.flatMap(cat =>
    (cat.commands || []).map(cmd => ({cat, cmd}))
  );
  // Counts
  document.getElementById('cat-count').textContent = state.categories.length;
  document.getElementById('cmd-count').textContent = state.flatCommands.length;
  document.getElementById('search-cmd-count').textContent = state.flatCommands.length;
  document.getElementById('foot-cmd-count').textContent = state.flatCommands.length;
  document.getElementById('foot-cat-count').textContent = state.categories.length;

  // Sidebar
  const list = document.getElementById('categories');
  list.innerHTML = '';
  for (const c of state.categories) {
    const li = document.createElement('li');
    li.dataset.key = c.key;
    li.innerHTML = `
      <span class="icon">${c.icon}</span>
      <span class="label">${escapeHTML(c.label)}</span>
      <span class="count">${(c.commands || []).length}</span>
    `;
    li.addEventListener('click', () => selectCategory(c.key));
    list.appendChild(li);
  }

  // Welcome cards
  const grid = document.getElementById('welcome-grid');
  grid.innerHTML = '';
  for (const c of state.categories) {
    const card = document.createElement('div');
    card.className = 'card';
    const cmdCount = (c.commands || []).length;
    card.innerHTML = `
      <span class="icon">${c.icon}</span>
      <div class="label">${escapeHTML(c.label)}</div>
      <div class="count">${cmdCount} command${cmdCount === 1 ? '' : 's'}</div>
    `;
    card.addEventListener('click', () => selectCategory(c.key));
    card.addEventListener('mousemove', (e) => {
      const r = card.getBoundingClientRect();
      card.style.setProperty('--mx', `${e.clientX - r.left}px`);
      card.style.setProperty('--my', `${e.clientY - r.top}px`);
    });
    grid.appendChild(card);
  }

  renderRecent();
  renderFavorites();
}

/* --------------------------------- Recent / Favorites ------------------- */
function findCmd(category, command) {
  const cat = state.categories.find(c => c.key === category);
  if (!cat) return null;
  const cmd = cat.commands.find(c => c.name === command);
  return cmd ? {cat, cmd} : null;
}

function renderRecent() {
  const recent = storage.getRecent();
  const section = document.getElementById('recent-section');
  const grid = document.getElementById('recent-grid');
  if (!recent.length) {
    section.classList.add('hidden');
    return;
  }
  section.classList.remove('hidden');
  grid.innerHTML = '';
  for (const r of recent.slice(0, 8)) {
    const found = findCmd(r.category, r.command);
    if (!found) continue;
    const card = makeCommandCard(found.cat, found.cmd, 'recent-card');
    grid.appendChild(card);
  }
}

function renderFavorites() {
  const favs = storage.getFavorites();
  const section = document.getElementById('favorites-section');
  const grid = document.getElementById('favorites-grid');
  if (!favs.length) {
    section.classList.add('hidden');
    return;
  }
  section.classList.remove('hidden');
  grid.innerHTML = '';
  for (const f of favs) {
    const found = findCmd(f.category, f.command);
    if (!found) continue;
    const card = makeCommandCard(found.cat, found.cmd, 'favorite-card');
    grid.appendChild(card);
  }
}

function makeCommandCard(cat, cmd, extraClass = '') {
  const card = document.createElement('div');
  card.className = `card ${extraClass}`.trim();
  card.innerHTML = `
    <span class="icon">${cat.icon}</span>
    <div class="label">${escapeHTML(cmd.name)}</div>
    <div class="count">${escapeHTML(cat.label)} · ${escapeHTML(cmd.help || '')}</div>
  `;
  card.addEventListener('click', () => {
    selectCategory(cat.key);
    selectCommand(cat.key, cmd);
  });
  return card;
}

document.getElementById('clear-recent').addEventListener('click', (e) => {
  e.stopPropagation();
  storage.clearRecent();
  renderRecent();
  toast('Recent cleared');
});

/* --------------------------------- Category / Command selection -------- */
function selectCategory(key) {
  _selectCategoryNoHash(key);
  setHash(key);
}
function _selectCategoryNoHash(key) {
  state.currentCategory = key;
  document.querySelectorAll('#categories li').forEach(li => {
    li.classList.toggle('active', li.dataset.key === key);
  });
  const cat = state.categories.find(c => c.key === key);
  if (!cat) return;

  document.getElementById('cmd-cat-title').textContent = `${cat.icon}  ${cat.label}`;
  document.getElementById('cmd-cat-desc').textContent =
    `${cat.commands.length} command${cat.commands.length === 1 ? '' : 's'} available`;

  const list = document.getElementById('commands-list');
  list.innerHTML = '';
  cat.commands.forEach((cmd, i) => {
    const li = document.createElement('li');
    li.dataset.idx = i;
    const fav = storage.isFavorite(key, cmd.name) ? ' ⭐' : '';
    li.innerHTML = `
      <div class="name">${escapeHTML(cmd.name)}${fav}</div>
      <div class="help">${escapeHTML(cmd.help || '')}</div>
    `;
    li.addEventListener('click', () => selectCommand(key, cmd));
    list.appendChild(li);
  });
  state.cmdListIndex = -1;
  showView('commands');
}

async function selectCommand(category, cmd) {
  await _selectCommandNoHash(category, cmd);
  setHash(`${category}/${cmd.name}`);
}

async function _selectCommandNoHash(category, cmd) {
  state.currentCommand = cmd.name;
  let schemaData;
  try {
    schemaData = await api.getSchema(category, cmd.name);
  } catch (e) {
    toast(`Schema error: ${e.message}`, 'error');
    return;
  }
  const schema = schemaData.args || [];

  showView('form');
  document.getElementById('output').classList.add('hidden');

  const cat = state.categories.find(c => c.key === category);
  document.getElementById('form-title').textContent = `${cat.icon}  ${cat.label}  →  ${cmd.name}`;
  document.getElementById('form-help').textContent = cmd.help || '';
  updateFavoriteBtn();

  const fieldsContainer = document.getElementById('form-fields');
  fieldsContainer.innerHTML = '';
  state.fieldRefs = [];

  if (schema.length === 0) {
    const note = document.createElement('div');
    note.className = 'muted';
    note.textContent = 'No arguments. Click Run.';
    fieldsContainer.appendChild(note);
  } else {
    for (const a of schema) {
      const field = renderField(a);
      if (field) {
        fieldsContainer.appendChild(field.el);
        state.fieldRefs.push({arg: a, getValue: field.getValue});
      }
    }
  }
  updateCommandPreview();
  renderBreadcrumbs();
  populatePresetSelect();
  updateSampleVisibility();
}

function updateFavoriteBtn() {
  const isFav = storage.isFavorite(state.currentCategory, state.currentCommand);
  const btn = document.getElementById('favorite-btn');
  btn.textContent = isFav ? '⭐' : '☆';
  btn.classList.toggle('active', isFav);
  btn.title = isFav ? 'Remove from favorites' : 'Add to favorites';
}

document.getElementById('favorite-btn').addEventListener('click', () => {
  const added = storage.toggleFavorite(state.currentCategory, state.currentCommand);
  toast(added ? '⭐ Added to favorites' : 'Removed from favorites');
  updateFavoriteBtn();
  renderFavorites();
});

/* --------------------------------- Field rendering ---------------------- */
function makeFileSelect() {
  const sel = document.createElement('select');
  const update = () => {
    sel.innerHTML = '<option value="">— pick from workspace —</option>';
    for (const f of state.workspaceFiles) {
      if (f.kind === 'file') {
        const o = document.createElement('option');
        o.value = f.name;
        o.textContent = f.name;
        sel.appendChild(o);
      }
    }
  };
  update();
  sel.addEventListener('focus', update);
  return {sel, update};
}

function setupFileFieldDrop(field, onFile) {
  field.addEventListener('dragover', (e) => {
    e.preventDefault();
    e.stopPropagation();
    field.classList.add('drag-active');
  });
  field.addEventListener('dragleave', () => field.classList.remove('drag-active'));
  field.addEventListener('drop', async (e) => {
    e.preventDefault();
    e.stopPropagation();
    field.classList.remove('drag-active');
    const files = e.dataTransfer.files;
    if (!files.length) return;
    toast(`Uploading ${files.length} file(s)…`);
    const result = await api.upload(files);
    if (result.files && result.files.length) {
      onFile(result.files[0].name);
      await refreshFiles();
      toast(`Uploaded ${result.files.length} file(s) ✓`, 'success');
    }
  });
}

function renderField(arg) {
  if (arg.name === 'cmd') return null;

  const wrap = document.createElement('div');
  wrap.className = 'field';

  const label = document.createElement('label');
  const flagText = arg.positional ? arg.name : (arg.flags[0] || arg.name);
  label.innerHTML = `<code>${escapeHTML(flagText)}</code>${arg.required ? ' <span class="required">*</span>' : ''}`;

  if (arg.type === 'bool') {
    const row = document.createElement('div');
    row.className = 'checkbox-row';
    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.checked = !!arg.default;
    cb.addEventListener('change', updateCommandPreview);
    row.appendChild(cb);
    row.appendChild(label);
    wrap.appendChild(row);
    if (arg.help) {
      const h = document.createElement('div');
      h.className = 'hint';
      h.textContent = arg.help;
      wrap.appendChild(h);
    }
    return {el: wrap, getValue: () => cb.checked ? {flag: arg.flags[0], type: 'flag'} : null};
  }

  wrap.appendChild(label);
  if (arg.help) {
    const hint = document.createElement('div');
    hint.className = 'hint';
    let text = arg.help;
    if (arg.default != null && arg.default !== false && arg.default !== '') text += `  (default: ${arg.default})`;
    hint.textContent = text;
    wrap.appendChild(hint);
  }

  // Multi-value
  if (arg.nargs === '+' || arg.nargs === '*') {
    const container = document.createElement('div');
    container.className = 'multi';
    const inputs = [];

    function addRow(initial = '') {
      const row = document.createElement('div');
      row.className = 'row';
      const inp = document.createElement('input');
      inp.type = 'text';
      inp.value = initial;
      inp.placeholder = arg.likely_file ? 'filename in workspace' : 'value';
      inp.addEventListener('input', updateCommandPreview);

      if (arg.likely_file) {
        const {sel} = makeFileSelect();
        sel.addEventListener('change', () => {
          if (sel.value) { inp.value = sel.value; updateCommandPreview(); }
        });
        row.appendChild(sel);
        setupFileFieldDrop(row, (filename) => { inp.value = filename; updateCommandPreview(); });
      }
      row.appendChild(inp);

      const rm = document.createElement('button');
      rm.type = 'button';
      rm.textContent = '✕';
      rm.className = 'rm-btn';
      rm.addEventListener('click', () => {
        const i = inputs.indexOf(inp);
        if (i >= 0) inputs.splice(i, 1);
        row.remove();
        updateCommandPreview();
      });
      row.appendChild(rm);

      container.insertBefore(row, addBtn);
      inputs.push(inp);
    }

    const addBtn = document.createElement('button');
    addBtn.type = 'button';
    addBtn.className = 'add-btn';
    addBtn.textContent = '+ Add another';
    addBtn.addEventListener('click', () => addRow());
    container.appendChild(addBtn);
    addRow();

    wrap.appendChild(container);
    return {
      el: wrap,
      getValue: () => {
        const vals = inputs.map(i => i.value).filter(v => v.trim());
        return vals.length ? {values: vals, arg} : null;
      },
    };
  }

  // Choices → select
  if (arg.choices && arg.choices.length) {
    const sel = document.createElement('select');
    if (!arg.required) {
      const opt = document.createElement('option');
      opt.value = '';
      opt.textContent = '— default —';
      sel.appendChild(opt);
    }
    for (const c of arg.choices) {
      const opt = document.createElement('option');
      opt.value = c;
      opt.textContent = c;
      if (arg.default === c) opt.selected = true;
      sel.appendChild(opt);
    }
    sel.addEventListener('change', updateCommandPreview);
    wrap.appendChild(sel);
    return {el: wrap, getValue: () => sel.value ? {value: sel.value, arg} : null};
  }

  // File input
  if (arg.likely_file && !arg.likely_output_file) {
    const row = document.createElement('div');
    row.className = 'file-row';
    const {sel} = makeFileSelect();
    const inp = document.createElement('input');
    inp.type = 'text';
    inp.placeholder = arg.default != null ? String(arg.default) : 'filename or drop a file here';
    sel.addEventListener('change', () => {
      if (sel.value) { inp.value = sel.value; updateCommandPreview(); }
    });
    inp.addEventListener('input', updateCommandPreview);
    row.appendChild(sel);
    row.appendChild(inp);
    wrap.appendChild(row);
    setupFileFieldDrop(row, (filename) => { inp.value = filename; updateCommandPreview(); });
    return {el: wrap, getValue: () => inp.value ? {value: inp.value, arg} : null};
  }

  // Output filename / outdir
  if (arg.likely_output_file) {
    const inp = document.createElement('input');
    inp.type = 'text';
    inp.placeholder = arg.default != null ? String(arg.default) : 'output name';
    inp.addEventListener('input', updateCommandPreview);
    wrap.appendChild(inp);
    return {
      el: wrap,
      getValue: () => {
        if (inp.value) return {value: inp.value, arg};
        if (arg.default != null && arg.default !== '') return {value: String(arg.default), arg};
        return null;
      },
    };
  }

  // Number
  if (arg.type === 'int' || arg.type === 'float') {
    const inp = document.createElement('input');
    inp.type = 'number';
    if (arg.type === 'float') inp.step = 'any';
    if (arg.default != null && arg.default !== false) inp.placeholder = String(arg.default);
    inp.addEventListener('input', updateCommandPreview);
    wrap.appendChild(inp);
    return {el: wrap, getValue: () => inp.value !== '' ? {value: inp.value, arg} : null};
  }

  // Text default
  const inp = document.createElement('input');
  inp.type = 'text';
  if (arg.default != null && arg.default !== false && arg.default !== '') inp.placeholder = String(arg.default);
  inp.addEventListener('input', updateCommandPreview);
  wrap.appendChild(inp);
  return {el: wrap, getValue: () => inp.value ? {value: inp.value, arg} : null};
}

function escapeHTML(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g,
    c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
}

/* --------------------------------- Build args & preview ----------------- */
function buildArgs() {
  const positional = [];
  const optional = [];
  for (const ref of state.fieldRefs || []) {
    const v = ref.getValue();
    if (v === null || v === undefined) continue;
    const a = ref.arg;
    if (v.type === 'flag') {
      optional.push(v.flag);
    } else if (v.values) {
      if (a.positional) positional.push(...v.values);
      else { optional.push(a.flags[0]); optional.push(...v.values); }
    } else {
      if (a.positional) positional.push(v.value);
      else { optional.push(a.flags[0]); optional.push(v.value); }
    }
  }
  return [...positional, ...optional];
}

function shellQuote(s) {
  return /[\s"'$`!]/.test(s) ? `"${s.replace(/"/g, '\\"')}"` : s;
}

function updateCommandPreview() {
  const argv = buildArgs();
  const quoted = argv.map(shellQuote);
  const cmd = `python tk.py ${state.currentCategory} ${state.currentCommand}${quoted.length ? ' ' + quoted.join(' ') : ''}`;
  document.getElementById('cmd-preview').textContent = cmd;
}

document.getElementById('cmd-copy-btn').addEventListener('click', async () => {
  const text = document.getElementById('cmd-preview').textContent;
  try {
    await navigator.clipboard.writeText(text);
    toast('CLI command copied ✓', 'success');
  } catch (e) {
    toast(`Copy failed: ${e.message}`, 'error');
  }
});

/* --------------------------------- Run ---------------------------------- */
document.getElementById('run-btn').addEventListener('click', runCurrent);

async function runCurrent() {
  if (state.isRunning) return;
  const btn = document.getElementById('run-btn');
  const args = buildArgs();
  state.isRunning = true;
  state.runStart = Date.now();
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Running…';
  document.getElementById('form').classList.add('running');
  const elapsedEl = document.getElementById('run-elapsed');
  elapsedEl.textContent = '';
  state.runTimer = setInterval(() => {
    const e = ((Date.now() - state.runStart) / 1000).toFixed(1);
    btn.innerHTML = `<span class="spinner"></span> Running… ${e}s`;
  }, 100);

  try {
    const result = await api.run(state.currentCategory, state.currentCommand, args);
    state.lastResult = result;
    storage.addRecent(state.currentCategory, state.currentCommand);
    showResult(result);
  } catch (e) {
    toast(`Error: ${e.message}`, 'error');
  } finally {
    clearInterval(state.runTimer);
    state.isRunning = false;
    btn.disabled = false;
    btn.innerHTML = '▶ Run  <span class="kbd-inline"><kbd>Ctrl</kbd>+<kbd>↵</kbd></span>';
    document.getElementById('form').classList.remove('running');
    const e = ((Date.now() - state.runStart) / 1000).toFixed(2);
    elapsedEl.textContent = `· ${e}s`;
  }
}

document.getElementById('reset-btn').addEventListener('click', () => {
  const cat = state.categories.find(c => c.key === state.currentCategory);
  const cmd = cat?.commands.find(c => c.name === state.currentCommand);
  if (cmd) selectCommand(state.currentCategory, cmd);
});

document.querySelectorAll('.btn-back').forEach(b => {
  b.addEventListener('click', () => {
    const target = b.dataset.back;
    if (target === 'welcome') goHome();
    else showView(target);
  });
});

/* --------------------------------- Show result -------------------------- */
function showResult(result) {
  document.getElementById('output').classList.remove('hidden');
  document.getElementById('output-stdout').textContent = result.stdout || '(no output)';
  document.getElementById('output-stderr').textContent = result.stderr || '(none)';

  const stderrHas = (result.stderr || '').trim().length > 0;
  const stderrDot = document.getElementById('stderr-dot');
  stderrDot.classList.toggle('hidden', !stderrHas);
  stderrDot.classList.toggle('error', result.rc !== 0);

  const newFiles = result.new_files || [];
  const newDirs = result.new_dirs || [];
  const filesMark = document.getElementById('files-count-mark');
  const fileTotal = newFiles.length + newDirs.length;
  filesMark.textContent = fileTotal;
  filesMark.classList.toggle('hidden', fileTotal === 0);

  if (result.rc === 0) {
    toast('✓ Done', 'success');
  } else {
    toast(`Exit code: ${result.rc}`, 'error');
    if (stderrHas) selectTab('stderr');
  }

  const filesList = document.getElementById('output-files');
  filesList.innerHTML = '';
  const previewArea = document.getElementById('output-preview');
  previewArea.innerHTML = '';

  for (const name of newFiles) {
    const li = document.createElement('li');
    const url = `/api/files/${encodeURIComponent(name)}`;
    const ext = (name.split('.').pop() || '').toLowerCase();
    li.innerHTML = `
      <span>${fileIcon(ext)}</span>
      <a href="${url}" target="_blank" download="${escapeHTML(name)}">${escapeHTML(name)}</a>
    `;
    filesList.appendChild(li);
    addPreview(previewArea, name, url, ext);
  }
  for (const name of newDirs) {
    const li = document.createElement('li');
    li.innerHTML = `<span>📁</span><span>${escapeHTML(name)}/</span><span class="size">(folder)</span>`;
    filesList.appendChild(li);
  }

  if (newFiles.length && previewArea.children.length) {
    selectTab('preview');
  } else if (newFiles.length || newDirs.length) {
    selectTab('files');
  } else if (result.rc !== 0 && stderrHas) {
    selectTab('stderr');
  } else {
    selectTab('stdout');
  }

  refreshFiles();
}

function addPreview(container, name, url, ext) {
  if (['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'svg', 'ico'].includes(ext)) {
    const img = document.createElement('img');
    img.src = url;
    img.alt = name;
    img.loading = 'lazy';
    img.addEventListener('click', () => openExpand(name, () => {
      const i = document.createElement('img');
      i.src = url;
      return i;
    }));
    container.appendChild(img);
  } else if (['mp4', 'webm', 'mov', 'mkv'].includes(ext)) {
    const v = document.createElement('video');
    v.src = url;
    v.controls = true;
    container.appendChild(v);
  } else if (['mp3', 'wav', 'ogg', 'flac', 'aac', 'm4a'].includes(ext)) {
    const a = document.createElement('audio');
    a.src = url;
    a.controls = true;
    container.appendChild(a);
  } else if (ext === 'pdf') {
    const ifr = document.createElement('iframe');
    ifr.src = url;
    container.appendChild(ifr);
  } else if (['txt', 'md', 'json', 'csv', 'yaml', 'yml', 'xml', 'html', 'h', 'c', 'cpp',
              'js', 'py', 'log', 'ini', 'toml', 'tsv'].includes(ext)) {
    fetch(url).then(r => r.text()).then(t => {
      const pre = document.createElement('pre');
      const truncated = t.length > 50000 ? t.substring(0, 50000) + '\n\n... [truncated]' : t;
      pre.textContent = truncated;
      container.appendChild(pre);
    });
  }
}

function fileIcon(ext) {
  if (['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'svg'].includes(ext)) return '🖼️';
  if (['mp4', 'webm', 'mov', 'mkv', 'avi'].includes(ext)) return '🎬';
  if (['mp3', 'wav', 'ogg', 'flac', 'aac'].includes(ext)) return '🎵';
  if (ext === 'pdf') return '📕';
  if (['txt', 'md', 'log'].includes(ext)) return '📄';
  if (['json', 'yaml', 'yml', 'xml', 'csv', 'toml'].includes(ext)) return '📊';
  if (['zip', 'tar', 'gz', 'bz2', 'xz', '7z'].includes(ext)) return '📦';
  if (['c', 'h', 'cpp', 'js', 'py'].includes(ext)) return '⚙️';
  return '📄';
}

function selectTab(name) {
  document.querySelectorAll('.output-tabs .tab').forEach(b => b.classList.toggle('active', b.dataset.tab === name));
  document.querySelectorAll('.tab-content').forEach(c => c.classList.toggle('active', c.id === 'tab-' + name));
}
document.querySelectorAll('.output-tabs .tab').forEach(t => {
  t.addEventListener('click', () => selectTab(t.dataset.tab));
});

/* --------------------------------- Output: copy & expand ---------------- */
document.getElementById('copy-btn').addEventListener('click', async () => {
  const activeTab = document.querySelector('.output-tabs .tab.active').dataset.tab;
  const el = document.getElementById('tab-' + activeTab);
  const text = el.innerText;
  try {
    await navigator.clipboard.writeText(text);
    toast('Copied to clipboard ✓', 'success');
  } catch (e) {
    toast(`Copy failed: ${e.message}`, 'error');
  }
});

document.getElementById('expand-btn').addEventListener('click', () => {
  const activeTab = document.querySelector('.output-tabs .tab.active').dataset.tab;
  const src = document.getElementById('tab-' + activeTab);
  openExpand(activeTab, () => src.cloneNode(true));
});

function openExpand(title, makeNode) {
  document.getElementById('expand-title').textContent = title;
  const target = document.getElementById('expand-content');
  target.innerHTML = '';
  target.appendChild(makeNode());
  document.getElementById('expand-overlay').classList.remove('hidden');
}
function closeExpand() {
  document.getElementById('expand-overlay').classList.add('hidden');
}
document.getElementById('expand-close').addEventListener('click', closeExpand);

/* --------------------------------- Files panel -------------------------- */
async function refreshFiles() {
  const data = await api.listFiles();
  const before = state.workspaceFiles.length;
  state.workspaceFiles = data.files || [];
  const fc = document.getElementById('file-count');
  fc.textContent = state.workspaceFiles.length;
  if (state.workspaceFiles.length > before) {
    fc.classList.remove('pulse');
    void fc.offsetWidth;
    fc.classList.add('pulse');
  }
  document.getElementById('ws-empty').classList.toggle('hidden', state.workspaceFiles.length > 0);

  const list = document.getElementById('files-list');
  list.innerHTML = '';
  for (const f of state.workspaceFiles) {
    const li = document.createElement('li');
    if (f.kind === 'file') {
      const ext = (f.name.split('.').pop() || '').toLowerCase();
      li.innerHTML = `
        <span>${fileIcon(ext)}</span>
        <span class="name"><a href="/api/files/${encodeURIComponent(f.name)}" target="_blank" download="${escapeHTML(f.name)}">${escapeHTML(f.name)}</a></span>
        <span class="size">${formatBytes(f.size)}</span>
        <button title="Delete">✕</button>
      `;
    } else {
      li.innerHTML = `
        <span>📁</span>
        <span class="name">${escapeHTML(f.name)}/</span>
        <span class="size">${f.size} files</span>
        <button title="Delete">✕</button>
      `;
    }
    li.querySelector('button').addEventListener('click', async () => {
      await api.deleteFile(f.name);
      refreshFiles();
    });
    list.appendChild(li);
  }
}

function formatBytes(n) {
  if (n < 1024) return n + ' B';
  if (n < 1024 * 1024) return (n / 1024).toFixed(1) + ' KB';
  if (n < 1024 * 1024 * 1024) return (n / 1024 / 1024).toFixed(1) + ' MB';
  return (n / 1024 / 1024 / 1024).toFixed(1) + ' GB';
}

document.getElementById('files-btn').addEventListener('click', toggleFilesPanel);
function toggleFilesPanel() {
  document.getElementById('files-panel').classList.toggle('hidden');
  refreshFiles();
}
document.getElementById('files-close').addEventListener('click', () => {
  document.getElementById('files-panel').classList.add('hidden');
});
document.getElementById('files-clear').addEventListener('click', async () => {
  if (state.workspaceFiles.length === 0) return;
  if (confirm(`Delete all ${state.workspaceFiles.length} workspace items?`)) {
    await api.clearWorkspace();
    refreshFiles();
    toast('Workspace cleared', 'info');
  }
});
document.getElementById('upload-input').addEventListener('change', async (e) => {
  const files = e.target.files;
  if (!files.length) return;
  toast(`Uploading ${files.length} file(s)…`);
  await api.upload(files);
  toast('Uploaded ✓', 'success');
  e.target.value = '';
  refreshFiles();
});
document.getElementById('hero-upload').addEventListener('click', () => {
  document.getElementById('files-panel').classList.remove('hidden');
  document.getElementById('upload-input').click();
});
document.getElementById('hero-search').addEventListener('click', openPalette);
document.getElementById('hero-list').addEventListener('click', openPalette);
document.getElementById('search-btn').addEventListener('click', openPalette);
document.getElementById('brand').addEventListener('click', goHome);

/* --------------------------------- Drag & drop (global) ----------------- */
let dragDepth = 0;
document.body.addEventListener('dragenter', (e) => {
  if (e.dataTransfer && e.dataTransfer.types && e.dataTransfer.types.includes('Files')) {
    dragDepth++;
    document.getElementById('drop-overlay').classList.remove('hidden');
  }
});
document.body.addEventListener('dragleave', (e) => {
  dragDepth = Math.max(0, dragDepth - 1);
  if (dragDepth === 0) document.getElementById('drop-overlay').classList.add('hidden');
});
document.body.addEventListener('dragover', (e) => e.preventDefault());
document.body.addEventListener('drop', async (e) => {
  e.preventDefault();
  dragDepth = 0;
  document.getElementById('drop-overlay').classList.add('hidden');
  // If a field handler stopped propagation, this won't fire; otherwise upload globally
  if (e.dataTransfer.files.length > 0) {
    toast(`Uploading ${e.dataTransfer.files.length} file(s)…`);
    await api.upload(e.dataTransfer.files);
    toast('Uploaded ✓', 'success');
    refreshFiles();
  }
});

/* --------------------------------- Command palette ---------------------- */
function openPalette() {
  const p = document.getElementById('palette');
  p.classList.remove('hidden');
  const inp = document.getElementById('palette-input');
  inp.value = '';
  inp.focus();
  state.paletteIndex = 0;
  renderPalette('');
}
function closePalette() {
  document.getElementById('palette').classList.add('hidden');
}
function renderPalette(query) {
  const list = document.getElementById('palette-results');
  list.innerHTML = '';
  query = query.toLowerCase().trim();
  const results = [];
  // Score: substring match preferred, then fuzzy subsequence
  for (const c of state.flatCommands) {
    const hay = `${c.cat.label} ${c.cmd.name} ${c.cmd.help}`.toLowerCase();
    let score = 0;
    if (!query) { score = 1; }
    else if (c.cmd.name.toLowerCase().includes(query)) { score = 100; }
    else if (hay.includes(query)) { score = 50; }
    else if (fuzzyMatch(hay, query)) { score = 10; }
    if (score > 0) results.push({...c, _score: score});
  }
  results.sort((a, b) => b._score - a._score);
  state.paletteResults = results.slice(0, 50);
  if (state.paletteIndex >= state.paletteResults.length) state.paletteIndex = 0;
  state.paletteResults.forEach((r, i) => {
    const li = document.createElement('li');
    if (i === state.paletteIndex) li.className = 'selected';
    li.innerHTML = `
      <span class="icon">${r.cat.icon}</span>
      <span class="path">${escapeHTML(r.cat.label)}</span>
      <code>${escapeHTML(r.cmd.name)}</code>
      <span class="help">${escapeHTML(r.cmd.help || '')}</span>
    `;
    li.addEventListener('click', () => {
      closePalette();
      selectCategory(r.cat.key);
      selectCommand(r.cat.key, r.cmd);
    });
    list.appendChild(li);
  });
  if (state.paletteResults.length === 0) {
    list.innerHTML = '<li class="empty">No commands match.</li>';
  }
}
function fuzzyMatch(text, query) {
  let qi = 0;
  for (let i = 0; i < text.length && qi < query.length; i++) {
    if (text[i] === query[qi]) qi++;
  }
  return qi === query.length;
}
document.getElementById('palette').addEventListener('click', (e) => {
  if (e.target.id === 'palette') closePalette();
});
document.getElementById('palette-input').addEventListener('input', (e) => {
  state.paletteIndex = 0;
  renderPalette(e.target.value);
});
document.getElementById('palette-input').addEventListener('keydown', (e) => {
  if (e.key === 'ArrowDown') {
    e.preventDefault();
    state.paletteIndex = Math.min(state.paletteIndex + 1, state.paletteResults.length - 1);
    renderPalette(e.target.value);
    scrollSelectedIntoView('#palette-results');
  } else if (e.key === 'ArrowUp') {
    e.preventDefault();
    state.paletteIndex = Math.max(0, state.paletteIndex - 1);
    renderPalette(e.target.value);
    scrollSelectedIntoView('#palette-results');
  } else if (e.key === 'Enter') {
    const r = state.paletteResults[state.paletteIndex];
    if (r) {
      closePalette();
      selectCategory(r.cat.key);
      selectCommand(r.cat.key, r.cmd);
    }
  } else if (e.key === 'Tab') {
    e.preventDefault();
    const r = state.paletteResults[state.paletteIndex];
    if (r) {
      const added = storage.toggleFavorite(r.cat.key, r.cmd.name);
      toast(added ? `⭐ Pinned ${r.cmd.name}` : `Unpinned ${r.cmd.name}`);
      renderFavorites();
    }
  } else if (e.key === 'Escape') {
    closePalette();
  }
});
function scrollSelectedIntoView(parentSel) {
  const el = document.querySelector(`${parentSel} li.selected`);
  if (el) el.scrollIntoView({block: 'nearest'});
}

/* --------------------------------- Shortcuts modal ---------------------- */
function openShortcuts() { document.getElementById('shortcuts').classList.remove('hidden'); }
function closeShortcuts() { document.getElementById('shortcuts').classList.add('hidden'); }
document.getElementById('shortcuts-btn').addEventListener('click', openShortcuts);
document.getElementById('shortcuts-close').addEventListener('click', closeShortcuts);
document.getElementById('shortcuts').addEventListener('click', (e) => {
  if (e.target.id === 'shortcuts') closeShortcuts();
});

/* --------------------------------- Keyboard shortcuts (global) --------- */
document.addEventListener('keydown', (e) => {
  const inField = ['INPUT', 'TEXTAREA', 'SELECT'].includes(e.target.tagName);

  // Always-active shortcuts
  if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
    e.preventDefault(); openPalette(); return;
  }
  if (e.key === 'Escape') {
    if (!document.getElementById('palette').classList.contains('hidden')) closePalette();
    else if (!document.getElementById('shortcuts').classList.contains('hidden')) closeShortcuts();
    else if (!document.getElementById('expand-overlay').classList.contains('hidden')) closeExpand();
    else if (inField) e.target.blur();
    return;
  }
  if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
    if (!document.getElementById('form').classList.contains('hidden')) { e.preventDefault(); runCurrent(); }
    return;
  }

  // Skip if typing
  if (inField) return;

  if (e.key === '?') { e.preventDefault(); openShortcuts(); return; }
  if (e.key === 't' || e.key === 'T') { toggleTheme(); return; }
  if (e.key === 'w' || e.key === 'W') { toggleFilesPanel(); return; }
  if (e.key === 'h' || e.key === 'H') { goHome(); return; }
  if (e.key === 'Backspace') {
    const formVisible = !document.getElementById('form').classList.contains('hidden');
    const cmdsVisible = !document.getElementById('commands').classList.contains('hidden');
    if (formVisible) { showView('commands'); return; }
    if (cmdsVisible) { goHome(); return; }
  }

  // Command list navigation
  if (!document.getElementById('commands').classList.contains('hidden')) {
    const items = document.querySelectorAll('#commands-list li');
    if (e.key === 'ArrowDown' || e.key === 'j') {
      e.preventDefault();
      state.cmdListIndex = Math.min(state.cmdListIndex + 1, items.length - 1);
      updateCmdListSelection(items);
    } else if (e.key === 'ArrowUp' || e.key === 'k') {
      e.preventDefault();
      state.cmdListIndex = Math.max(0, state.cmdListIndex - 1);
      updateCmdListSelection(items);
    } else if (e.key === 'Enter') {
      const item = items[state.cmdListIndex];
      if (item) item.click();
    }
  }
});

function updateCmdListSelection(items) {
  items.forEach((it, i) => it.classList.toggle('selected', i === state.cmdListIndex));
  if (items[state.cmdListIndex]) items[state.cmdListIndex].scrollIntoView({block: 'nearest'});
}

/* --------------------------------- Sample fill -------------------------- */
function updateSampleVisibility() {
  const has = !!getSample(state.currentCategory, state.currentCommand);
  document.getElementById('sample-btn').style.display = has ? '' : 'none';
}

function applyValuesToForm(values) {
  for (const ref of state.fieldRefs || []) {
    const a = ref.arg;
    const flagKey = (a.flags && a.flags[0]);
    const v = values[a.name] != null ? values[a.name]
            : (flagKey && values[flagKey] != null ? values[flagKey] : null);
    if (v == null) continue;
    const el = ref.getValue.field || null;  // not exposed; use DOM lookup instead
  }
  // The fieldRefs don't expose set; do it by DOM walking the form fields in order.
  const fieldRows = document.getElementById('form-fields').children;
  let i = 0;
  for (const ref of state.fieldRefs || []) {
    const a = ref.arg;
    const flagKey = (a.flags && a.flags[0]);
    let v = values[a.name];
    if (v == null && flagKey) v = values[flagKey];
    if (v == null) { i++; continue; }
    const row = fieldRows[i];
    if (!row) { i++; continue; }
    if (a.type === 'bool') {
      const cb = row.querySelector('input[type="checkbox"]');
      if (cb) cb.checked = !!v;
    } else if (a.choices && a.choices.length) {
      const sel = row.querySelector('select');
      if (sel) sel.value = String(v);
    } else if (a.nargs === '+' || a.nargs === '*') {
      // For multi: clear existing and add new ones
      const rows = row.querySelectorAll('.row');
      const arr = Array.isArray(v) ? v : [v];
      // Remove all but first
      rows.forEach((r, ri) => { if (ri > 0) r.remove(); });
      const inputs = row.querySelectorAll('.row input[type="text"]');
      inputs[0].value = String(arr[0] ?? '');
      const addBtn = row.querySelector('.add-btn');
      for (let j = 1; j < arr.length; j++) {
        addBtn.click();
        const allInputs = row.querySelectorAll('.row input[type="text"]');
        allInputs[j].value = String(arr[j]);
      }
    } else {
      const txt = row.querySelector('input[type="text"], input[type="number"]');
      if (txt) txt.value = String(v);
    }
    i++;
  }
  updateCommandPreview();
}

document.getElementById('sample-btn').addEventListener('click', () => {
  const sample = getSample(state.currentCategory, state.currentCommand);
  if (!sample) return toast('No sample for this command');
  applyValuesToForm(sample);
  toast('✨ Sample loaded');
});

/* --------------------------------- Presets ------------------------------ */
function populatePresetSelect() {
  const sel = document.getElementById('preset-load');
  sel.innerHTML = '<option value="">Presets…</option>';
  const presets = storage.getPresets(state.currentCategory, state.currentCommand);
  if (!presets.length) {
    sel.innerHTML += '<option disabled>(none saved)</option>';
    return;
  }
  for (const p of presets) {
    const opt = document.createElement('option');
    opt.value = p.name;
    opt.textContent = p.name;
    sel.appendChild(opt);
  }
}

function readFormValues() {
  const out = {};
  const fieldRows = document.getElementById('form-fields').children;
  let i = 0;
  for (const ref of state.fieldRefs || []) {
    const a = ref.arg;
    const row = fieldRows[i++];
    if (!row) continue;
    if (a.type === 'bool') {
      const cb = row.querySelector('input[type="checkbox"]');
      out[a.name] = cb ? cb.checked : false;
    } else if (a.choices && a.choices.length) {
      const sel = row.querySelector('select');
      out[a.name] = sel ? sel.value : '';
    } else if (a.nargs === '+' || a.nargs === '*') {
      const inputs = row.querySelectorAll('.row input[type="text"]');
      out[a.name] = Array.from(inputs).map(i => i.value).filter(v => v.trim());
    } else {
      const txt = row.querySelector('input[type="text"], input[type="number"]');
      out[a.name] = txt ? txt.value : '';
    }
  }
  return out;
}

document.getElementById('preset-save-btn').addEventListener('click', () => {
  document.getElementById('preset-name-input').value = '';
  document.getElementById('preset-dialog').classList.remove('hidden');
  setTimeout(() => document.getElementById('preset-name-input').focus(), 50);
});
document.getElementById('preset-confirm').addEventListener('click', () => {
  const name = document.getElementById('preset-name-input').value.trim();
  if (!name) return toast('Enter a name', 'error');
  storage.savePreset(state.currentCategory, state.currentCommand, name, readFormValues());
  populatePresetSelect();
  document.getElementById('preset-dialog').classList.add('hidden');
  toast(`💾 Saved preset "${name}"`, 'success');
});
document.getElementById('preset-cancel').addEventListener('click', () =>
  document.getElementById('preset-dialog').classList.add('hidden'));
document.getElementById('preset-cancel-2').addEventListener('click', () =>
  document.getElementById('preset-dialog').classList.add('hidden'));
document.getElementById('preset-name-input').addEventListener('keydown', (e) => {
  if (e.key === 'Enter') document.getElementById('preset-confirm').click();
});
document.getElementById('preset-load').addEventListener('change', (e) => {
  const name = e.target.value;
  if (!name) return;
  const presets = storage.getPresets(state.currentCategory, state.currentCommand);
  const p = presets.find(x => x.name === name);
  if (p) { applyValuesToForm(p.values); toast(`Loaded preset "${name}"`); }
  e.target.value = '';
});

/* --------------------------------- Run history -------------------------- */
function renderHistory() {
  const list = document.getElementById('history-list');
  const h = storage.getHistory();
  document.getElementById('history-count').textContent = h.length;
  document.getElementById('history-empty').classList.toggle('hidden', h.length > 0);
  list.innerHTML = '';
  for (const entry of h) {
    const li = document.createElement('li');
    const when = new Date(entry.ts);
    const ago = relativeTime(when);
    li.innerHTML = `
      <div><span class="h-cmd">${escapeHTML(entry.category)} ${escapeHTML(entry.command)}</span></div>
      <div class="h-meta">
        <span class="h-rc ${entry.rc === 0 ? 'ok' : 'fail'}">rc=${entry.rc}</span>
        <span>${ago}</span>
      </div>
      <div class="h-args">${escapeHTML((entry.args || []).join(' ') || '(no args)')}</div>
    `;
    li.addEventListener('click', () => {
      const found = findCmd(entry.category, entry.command);
      if (!found) return toast('Command no longer exists', 'error');
      document.getElementById('history-panel').classList.add('hidden');
      selectCategory(entry.category);
      selectCommand(entry.category, found.cmd).then(() => {
        applyArgsArrayToForm(entry.args || []);
      });
    });
    list.appendChild(li);
  }
}

function relativeTime(d) {
  const sec = Math.floor((Date.now() - d.getTime()) / 1000);
  if (sec < 60) return `${sec}s ago`;
  if (sec < 3600) return `${Math.floor(sec / 60)}m ago`;
  if (sec < 86400) return `${Math.floor(sec / 3600)}h ago`;
  return `${Math.floor(sec / 86400)}d ago`;
}

function applyArgsArrayToForm(argv) {
  // Replay an argv list onto the current form.  Best-effort.
  // Walk argv, when we see a flag matching a non-positional arg, set its next value.
  // Otherwise consume positional in order.
  const positionalArgs = (state.fieldRefs || []).filter(r => r.arg.positional);
  const optionalByFlag = {};
  for (const r of state.fieldRefs || []) {
    if (!r.arg.positional) {
      for (const f of r.arg.flags) optionalByFlag[f] = r.arg;
    }
  }
  const values = {};
  let posIdx = 0;
  for (let i = 0; i < argv.length; i++) {
    const tok = argv[i];
    if (optionalByFlag[tok]) {
      const a = optionalByFlag[tok];
      if (a.type === 'bool') { values[a.name] = true; continue; }
      if (a.nargs === '+' || a.nargs === '*') {
        const vals = [];
        while (i + 1 < argv.length && !optionalByFlag[argv[i + 1]]) vals.push(argv[++i]);
        values[a.name] = vals;
      } else {
        values[a.name] = argv[++i];
      }
    } else if (posIdx < positionalArgs.length) {
      const r = positionalArgs[posIdx];
      const a = r.arg;
      if (a.nargs === '+' || a.nargs === '*') {
        const vals = [tok];
        while (i + 1 < argv.length && !optionalByFlag[argv[i + 1]]) vals.push(argv[++i]);
        values[a.name] = vals;
        posIdx++;
      } else {
        values[a.name] = tok;
        posIdx++;
      }
    }
  }
  applyValuesToForm(values);
}

document.getElementById('history-btn').addEventListener('click', () => {
  document.getElementById('history-panel').classList.toggle('hidden');
  renderHistory();
});
document.getElementById('history-close').addEventListener('click', () =>
  document.getElementById('history-panel').classList.add('hidden'));
document.getElementById('history-clear').addEventListener('click', () => {
  if (confirm('Clear all run history?')) {
    storage.clearHistory();
    renderHistory();
  }
});

// Hook into runCurrent to record history
const origRun = runCurrent;
runCurrent = async function() {
  if (state.isRunning) return;
  const args = buildArgs();
  await origRun.call(this);
  const result = state.lastResult || {rc: 0, stdout: '', stderr: ''};
  storage.addHistory({
    category: state.currentCategory,
    command: state.currentCommand,
    args,
    rc: result.rc,
  });
  document.getElementById('history-count').textContent = storage.getHistory().length;
};
// Replace the original run-btn click handler
document.getElementById('run-btn').replaceWith(document.getElementById('run-btn').cloneNode(true));
document.getElementById('run-btn').addEventListener('click', runCurrent);

/* --------------------------------- Prev / Next command ------------------ */
function neighborCommand(delta) {
  const cat = state.categories.find(c => c.key === state.currentCategory);
  if (!cat) return null;
  const i = cat.commands.findIndex(c => c.name === state.currentCommand);
  if (i < 0) return null;
  const j = (i + delta + cat.commands.length) % cat.commands.length;
  return cat.commands[j];
}
document.getElementById('prev-cmd-btn').addEventListener('click', () => {
  const c = neighborCommand(-1);
  if (c) selectCommand(state.currentCategory, c);
});
document.getElementById('next-cmd-btn').addEventListener('click', () => {
  const c = neighborCommand(1);
  if (c) selectCommand(state.currentCategory, c);
});

/* --------------------------------- Tour --------------------------------- */
function openTour() {
  document.getElementById('tour-cmd-count').textContent = state.flatCommands.length;
  document.getElementById('tour-cat-count').textContent = state.categories.length;
  document.getElementById('tour').classList.remove('hidden');
  showTourStep(1);
}
function closeTour() {
  document.getElementById('tour').classList.add('hidden');
  storage.markTourSeen();
}
function showTourStep(n) {
  document.querySelectorAll('.tour-step').forEach(s => s.classList.toggle('hidden', +s.dataset.step !== n));
  document.getElementById('tour-progress').textContent = `${n} / 4`;
  document.getElementById('tour-next').textContent = n === 4 ? 'Done' : 'Next →';
  document.getElementById('tour').dataset.step = n;
}
document.getElementById('tour-next').addEventListener('click', () => {
  const n = parseInt(document.getElementById('tour').dataset.step || '1', 10);
  if (n >= 4) closeTour();
  else showTourStep(n + 1);
});
document.getElementById('tour-skip').addEventListener('click', closeTour);
document.getElementById('tour').addEventListener('click', (e) => {
  if (e.target.id === 'tour') closeTour();
});

/* --------------------------------- Extra keyboard shortcuts ------------- */
document.addEventListener('keydown', (e) => {
  const inField = ['INPUT', 'TEXTAREA', 'SELECT'].includes(e.target.tagName);
  if (inField) return;
  if (e.key === 'y' || e.key === 'Y') {
    document.getElementById('history-panel').classList.toggle('hidden');
    renderHistory();
  }
  if ((e.ctrlKey || e.metaKey) && e.key === ']') {
    if (!document.getElementById('form').classList.contains('hidden')) {
      e.preventDefault();
      const c = neighborCommand(1);
      if (c) selectCommand(state.currentCategory, c);
    }
  }
  if ((e.ctrlKey || e.metaKey) && e.key === '[') {
    if (!document.getElementById('form').classList.contains('hidden')) {
      e.preventDefault();
      const c = neighborCommand(-1);
      if (c) selectCommand(state.currentCategory, c);
    }
  }
});

/* --------------------------------- Init --------------------------------- */
initTheme();
loadCategories().then(() => {
  refreshFiles();
  // Apply URL hash if present
  if (location.hash) applyHash();
  // First-visit tour
  if (!storage.tourSeen()) {
    setTimeout(openTour, 600);
  }
  document.getElementById('history-count').textContent = storage.getHistory().length;
});
