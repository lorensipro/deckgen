// Slide Preview : aperçu du transparent Beamer sous le curseur (fichiers YAML de build.py).
// JavaScript pur, sans dépendance : le dossier peut être lié directement dans ~/.vscode/extensions.
const vscode = require('vscode');
const cp = require('child_process');
const fs = require('fs');
const path = require('path');

let panel = null;          // WebviewPanel
let state = {              // état courant
  file: null, line: 0, slideIdx: -1, lang: null, audience: '', layer: -1,
  layers: 0, info: null, error: null, busy: false, dirty: false, follow: true,
  project: null, langs: ['fr'], audiences: [], ms: 0,
};
let cursorTimer = null, typingTimer = null;
let diagnostics = null;    // DiagnosticCollection (soulignements dans l'éditeur)

function slideStartLine(text, idx) {
  // ligne (0-based) du idx-ième transparent (règle : '- ' en colonne 0)
  const lines = text.split('\n'); let k = -1;
  for (let n = 0; n < lines.length; n++) if (/^-(\s|$)/.test(lines[n])) { k++; if (k === idx) return n; }
  return 0;
}

function excerpt(text, line1, column) {
  // extrait du source autour de la ligne (1-based), avec un marqueur
  if (!line1) return '';
  const lines = text.split('\n'); const out = [];
  for (let n = Math.max(0, line1 - 3); n < Math.min(lines.length, line1 + 2); n++) {
    const mark = (n === line1 - 1) ? '›' : ' ';
    out.push(`${mark} ${String(n + 1).padStart(4)} │ ${lines[n]}`);
    if (n === line1 - 1 && column) out.push(`       │ ${' '.repeat(Math.max(0, column - 1))}^`);
  }
  return out.join('\n');
}

function setDiagnostics(document, info, error) {
  if (!diagnostics) return;
  const list = [];
  const text = document.getText();
  const mk = (line1, msg, sev) => {
    const l = Math.max(0, Math.min(document.lineCount - 1, (line1 || 1) - 1));
    const range = document.lineAt(l).range;
    const d = new vscode.Diagnostic(range, msg, sev); d.source = 'slide-preview'; return d;
  };
  if (error) {
    let line = error.line;
    if (!line && state.mode === 'tikz' && error.tex_line) line = error.tex_line;       // l.N de pdflatex = ligne du fichier tikz
    if (!line && state.slideIdx >= 0) line = slideStartLine(text, state.slideIdx) + 1;   // erreur LaTeX : sur le transparent
    list.push(mk(line, error.error + (error.detail ? '\n' + error.detail.split('\n').slice(0, 6).join('\n') : ''), vscode.DiagnosticSeverity.Error));
    if (error.context_line && error.context_line !== error.line)
      list.push(mk(error.context_line, 'YAML : contexte de l\'erreur (clé commencée ici)', vscode.DiagnosticSeverity.Information));
  }
  for (const w of (info && info.warnings) || []) list.push(mk(w.line, w.message, vscode.DiagnosticSeverity.Warning));
  diagnostics.set(document.uri, list);
}

// ---------------------------------------------------------------- projet

function findProject(file) {
  // remonte jusqu'au dossier du cours, celui qui contient deck.yaml
  let dir = path.dirname(file);
  for (let i = 0; i < 6; i++) {
    if (fs.existsSync(path.join(dir, 'deck.yaml'))) return dir;
    const up = path.dirname(dir);
    if (up === dir) break;
    dir = up;
  }
  return null;
}

function readDeck(project) {
  // lecture minimale de deck.yaml (listes langs/audiences en ligne : [a, b, c])
  try {
    const t = fs.readFileSync(path.join(project, 'deck.yaml'), 'utf8');
    const list = (key) => {
      const m = t.match(new RegExp('^' + key + ':\\s*\\[([^\\]]*)\\]', 'm'));
      return m ? m[1].split(',').map(s => s.trim()).filter(Boolean) : [];
    };
    const lang = (t.match(/^lang:\s*(\w+)/m) || [])[1];
    return { langs: list('langs').length ? list('langs') : ['fr'], audiences: list('audiences'), lang: lang || 'fr' };
  } catch (e) { return { langs: ['fr'], audiences: [], lang: 'fr' }; }
}

function slideIndexAt(text, line0) {
  // même règle que build.py : un transparent commence à une ligne '- ' en colonne 0
  const lines = text.split('\n');
  let idx = -1;
  for (let n = 0; n <= Math.min(line0, lines.length - 1); n++) if (/^-(\s|$)/.test(lines[n])) idx++;
  return idx;
}

// ---------------------------------------------------------------- rendu

function isTikz(document) {
  return /\.(tikz|tex)$/i.test(document.fileName) && document.languageId !== 'yaml';
}
function isSupported(document) {
  return document && (document.languageId === 'yaml' || isTikz(document));
}

function scheduleFromCursor(editor, reason) {
  if (!editor || !isSupported(editor.document) || !panel || !state.follow) return;
  const file = editor.document.fileName;
  const project = findProject(file);
  if (!project) return;
  const tikz = isTikz(editor.document);
  const line0 = editor.selection.active.line;
  const idx = tikz ? -1 : slideIndexAt(editor.document.getText(), line0);
  const changedSlide = (file !== state.file) || (idx !== state.slideIdx);
  state.file = file; state.line = line0 + 1; state.slideIdx = idx; state.project = project; state.mode = tikz ? 'tikz' : 'yaml';
  const cfg = vscode.workspace.getConfiguration('slidePreview');
  if (reason === 'type' && !cfg.get('renderOnType')) return;
  if (reason === 'cursor' && !changedSlide) return;
  const delay = reason === 'type' ? cfg.get('typingDelay') : reason === 'save' ? 0 : cfg.get('cursorDelay');
  clearTimeout(cursorTimer);
  cursorTimer = setTimeout(() => render(editor.document), delay);
}

function render(document) {
  if (!panel || !state.project) return;
  if (state.busy) { state.dirty = true; return; }
  state.busy = true; state.dirty = false;
  const cfg = vscode.workspace.getConfiguration('slidePreview');
  const previewDir = path.join(state.project, 'build', 'preview');
  fs.mkdirSync(previewDir, { recursive: true });
  // le buffer (même non sauvegardé) est écrit dans un fichier temporaire du projet
  const tikz = state.mode === 'tikz';
  const tmp = path.join(previewDir, tikz ? 'current.tikz' : 'current.yaml');
  fs.writeFileSync(tmp, document.getText());
  // build.py du générateur : réglage slidePreview.buildScript, sinon celui du dépôt qui contient ce plugin
  const build = cfg.get('buildScript') || path.join(__dirname, '..', 'build.py');
  const args = tikz ? [build, '--tikz', state.file, '--buffer', tmp]
                    : [build, '--slide', `${tmp}:${state.line}`, '--origine', state.file];   // origine : deck et section du transparent
  if (state.lang) args.push('--lang', state.lang);
  if (state.audience) args.push('--audience', state.audience);
  const t0 = Date.now();
  post({ type: 'busy', busy: true });
  cp.execFile(cfg.get('python'), args, { cwd: state.project, maxBuffer: 4e6 }, (err, stdout, stderr) => {
    state.busy = false;
    state.ms = Date.now() - t0;
    const m = (stdout || '').split('\n').reverse().find(l => l.startsWith('PREVIEW_JSON '));
    let info = null;
    try { info = m ? JSON.parse(m.slice('PREVIEW_JSON '.length)) : null; } catch (e) { info = null; }
    if (info && !info.error) {
      state.info = info; state.error = null; state.errorObj = null; state.layers = info.layers;
      if (state.layer < 0 || state.layer >= info.layers) state.layer = info.layers - 1;
      setDiagnostics(document, info, null);
    } else {
      state.errorObj = info && info.error ? info : { error: (stderr || stdout || String(err)).slice(-1500), kind: 'exec' };
      state.error = state.errorObj.error;
      state.excerpt = excerpt(document.getText(), state.errorObj.line, state.errorObj.column);
      state.detail = state.errorObj.detail || '';
      setDiagnostics(document, null, state.errorObj);
    }
    update();
    if (state.dirty) render(document);
  });
}

function post(msg) { if (panel) panel.webview.postMessage(msg); }

function update() {
  if (!panel || !state.ready) return;
  const dir = state.info ? state.info.dir : null;
  let images = [];
  if (dir && !state.error) {
    for (let i = 0; i < state.layers; i++) {
      const p = path.join(dir, `slide-${i}.png`);
      try {   // image intégrée au message : indépendant des règles de ressources du webview
        images.push('data:image/png;base64,' + fs.readFileSync(p).toString('base64'));
      } catch (e) { state.error = `image manquante : ${p}`; }
    }
  }
  post({
    type: 'update', images, layer: state.layer, error: state.error, info: state.info, ms: state.ms,
    excerpt: state.error ? state.excerpt : '', detail: state.error ? state.detail : '',
    warnings: (state.info && state.info.warnings) || [],
    lang: state.lang, audience: state.audience, langs: state.langs, audiences: state.audiences,
    follow: state.follow, file: state.file ? path.basename(state.file) : '', busy: false,
  });
}

// ---------------------------------------------------------------- panneau

function openPanel(context) {
  const editor = vscode.window.activeTextEditor;
  if (panel) { panel.reveal(undefined, true); scheduleFromCursor(editor, 'save'); return; }
  const project = editor ? findProject(editor.document.fileName) : null;
  const deck = project ? readDeck(project) : { langs: ['fr'], audiences: [], lang: 'fr' };
  state.langs = deck.langs; state.audiences = deck.audiences; state.lang = state.lang || deck.lang;
  const roots = [vscode.Uri.file(path.join(context.extensionPath))];
  if (project) roots.push(vscode.Uri.file(path.join(project, 'build', 'preview')));
  panel = vscode.window.createWebviewPanel('slidePreview', 'Aperçu du transparent', { viewColumn: vscode.ViewColumn.Beside, preserveFocus: true },
    { enableScripts: true, retainContextWhenHidden: true, localResourceRoots: roots });
  panel.webview.html = html();
  panel.onDidDispose(() => { panel = null; state.ready = false; }, null, context.subscriptions);
  panel.onDidChangeViewState(e => { if (e.webviewPanel.visible) update(); }, null, context.subscriptions);
  panel.webview.onDidReceiveMessage(msg => {
    const ed = vscode.window.activeTextEditor;
    if (msg.type === 'ready')    { state.ready = true; update(); return; }
    if (msg.type === 'lang')     { state.lang = msg.value; rerender(); }
    if (msg.type === 'audience') { state.audience = msg.value; rerender(); }
    if (msg.type === 'layer')    { state.layer = msg.value; update(); }
    if (msg.type === 'follow')   { state.follow = msg.value; }
    if (msg.type === 'refresh')  { rerender(); }
    function rerender() {
      const doc = (ed && ed.document.fileName === state.file) ? ed.document
        : vscode.workspace.textDocuments.find(d => d.fileName === state.file);
      if (doc) render(doc); else update();
    }
  }, null, context.subscriptions);
  // si le projet change de dossier build (autre projet), il faudra rouvrir le panneau
  scheduleFromCursor(editor, 'save');
}

function html() {
  return `<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
  body { margin:0; font-family: var(--vscode-font-family); color: var(--vscode-foreground); background: var(--vscode-editor-background); }
  #bar { display:flex; gap:8px; align-items:center; padding:6px 8px; font-size:12px; border-bottom:1px solid var(--vscode-panel-border); flex-wrap:wrap; }
  select, button { font-size:12px; background: var(--vscode-input-background); color: var(--vscode-input-foreground); border:1px solid var(--vscode-input-border, transparent); border-radius:3px; padding:2px 6px; }
  button { cursor:pointer; }
  #status { margin-left:auto; opacity:0.75; }
  #img { display:block; width:100%; height:auto; }
  #wrap { padding:8px; }
  #err { white-space:pre-wrap; font-family: var(--vscode-editor-font-family); font-size:12px; color: var(--vscode-errorForeground); padding:8px; }
  #err .title { font-family: var(--vscode-font-family); font-weight:600; margin-bottom:6px; }
  #err pre { margin:6px 0; padding:6px; background: var(--vscode-textBlockQuote-background); color: var(--vscode-foreground); overflow-x:auto; }
  #warn { font-size:12px; color: var(--vscode-editorWarning-foreground, #c90); padding:4px 8px; white-space:pre-wrap; }
  .busy #img { opacity:0.55; transition: opacity .2s; }
</style></head><body>
<div id="bar">
  <label>Langue <select id="lang"></select></label>
  <label>Audience <select id="aud"><option value="">toutes</option></select></label>
  <span id="layers"></span>
  <label><input type="checkbox" id="follow" checked> suivre le curseur</label>
  <button id="refresh">↻</button>
  <span id="status"></span>
</div>
<div id="wrap"><div id="warn"></div><img id="img" alt=""><div id="err"></div><div id="hint" style="opacity:.6;padding:8px;font-size:12px">Placez le curseur dans un transparent d'un fichier YAML (ou dans un fichier .tikz) du projet.</div></div>
<script>
  const vscode = acquireVsCodeApi();
  const $ = id => document.getElementById(id);
  vscode.postMessage({ type: 'ready' });   // l'extension renvoie l'état courant (évite un message perdu au chargement)
  let cur = { images: [], layer: 0 };
  $('lang').onchange = e => vscode.postMessage({ type: 'lang', value: e.target.value });
  $('aud').onchange = e => vscode.postMessage({ type: 'audience', value: e.target.value });
  $('follow').onchange = e => vscode.postMessage({ type: 'follow', value: e.target.checked });
  $('refresh').onclick = () => vscode.postMessage({ type: 'refresh' });
  function fill(sel, values, current, keepFirst) {
    const first = keepFirst ? sel.options[0].outerHTML : '';
    sel.innerHTML = first + values.map(v => '<option value="' + v + '">' + v + '</option>').join('');
    sel.value = current || '';
  }
  function show(layer) {
    cur.layer = layer;
    $('img').src = cur.images[layer] || '';
    $('img').style.display = cur.images.length ? 'block' : 'none';
    const n = cur.images.length;
    $('layers').innerHTML = n > 1
      ? 'Couche <button id="prev">‹</button> ' + (layer + 1) + '/' + n + ' <button id="next">›</button>' : '';
    if (n > 1) {
      $('prev').onclick = () => vscode.postMessage({ type: 'layer', value: Math.max(0, layer - 1) });
      $('next').onclick = () => vscode.postMessage({ type: 'layer', value: Math.min(n - 1, layer + 1) });
    }
  }
  window.addEventListener('message', ev => {
    const m = ev.data;
    if (m.type === 'busy') { document.body.classList.toggle('busy', m.busy); return; }
    document.body.classList.remove('busy');
    $('hint').style.display = (m.images && m.images.length) || m.error ? 'none' : 'block';
    fill($('lang'), m.langs, m.lang, false);
    fill($('aud'), m.audiences, m.audience, true);
    $('follow').checked = m.follow;
    cur.images = m.images || [];
    const esc = t => String(t).replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
    $('err').innerHTML = m.error
      ? '<div class="title">' + esc(m.error) + '</div>'
        + (m.excerpt ? '<pre>' + esc(m.excerpt) + '</pre>' : '')
        + (m.detail ? '<pre>' + esc(m.detail) + '</pre>' : '')
      : '';
    $('warn').textContent = (m.warnings || []).map(w => '⚠ ligne ' + w.line + ' : ' + w.message).join('\\n');
    show(Math.min(m.layer, Math.max(0, cur.images.length - 1)));
    const i = m.info;
    $('status').textContent = m.error ? 'erreur' :
      (i ? (i.mode === 'tikz'
              ? (m.file + (i.used_by ? ' · dans ' + i.used_by : ' · seul') + ' · ' + m.ms + ' ms')
              : (m.file + ' · transparent ' + i.slide + '/' + i.total
                 + (i.hidden ? (i.hide_reason === 'hide' ? ' · MASQUÉ (hide: true)' : ' · masqué pour cette audience') : '')
                 + ' · ' + m.ms + ' ms')) : '');
  });
</script></body></html>`;
}

// ---------------------------------------------------------------- activation

function activate(context) {
  diagnostics = vscode.languages.createDiagnosticCollection('slide-preview');
  context.subscriptions.push(
    diagnostics,
    vscode.workspace.onDidCloseTextDocument(doc => diagnostics.delete(doc.uri)),
    vscode.commands.registerCommand('slidePreview.open', () => openPanel(context)),
    vscode.commands.registerCommand('slidePreview.refresh', () => {
      const ed = vscode.window.activeTextEditor; if (ed && panel) render(ed.document);
    }),
    vscode.window.onDidChangeTextEditorSelection(e => scheduleFromCursor(e.textEditor, 'cursor')),
    vscode.window.onDidChangeActiveTextEditor(ed => scheduleFromCursor(ed, 'cursor')),
    vscode.workspace.onDidSaveTextDocument(doc => {
      const ed = vscode.window.activeTextEditor;
      if (ed && ed.document === doc) scheduleFromCursor(ed, 'save');
    }),
    vscode.workspace.onDidChangeTextDocument(e => {
      const ed = vscode.window.activeTextEditor;
      if (ed && ed.document === e.document && e.contentChanges.length) {
        clearTimeout(typingTimer);
        typingTimer = setTimeout(() => scheduleFromCursor(ed, 'type'), 50);
      }
    }),
  );
}
function deactivate() {}
module.exports = { activate, deactivate, _test: { findProject, readDeck, slideIndexAt, slideStartLine, excerpt, html } };
