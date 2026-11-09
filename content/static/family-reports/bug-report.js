// Same note → immutable context → durable queue flow as Family Games.
let adapter = {}, draft = null, opened = false;
const copy = value => JSON.parse(JSON.stringify(value));
const newId = () => crypto.randomUUID ? crypto.randomUUID() : Array.from(crypto.getRandomValues(new Uint8Array(16)), b => b.toString(16).padStart(2, '0')).join('');
const labels = {queued:'Queued', running:'Fixing', fixed:'Fixed', needs_attention:'Needs attention', failed:'Failed'};
const endpoint = () => adapter.endpoint || '/api/bug-reports';

async function request(path, body) {
  const controller = new AbortController(), timer = setTimeout(() => controller.abort(), 20000);
  try {
    const csrf = document.querySelector('#csrf-source input')?.value;
    const response = await fetch(path, {method:body === undefined ? 'GET' : 'POST',
      credentials:'same-origin', cache:'no-store', signal:controller.signal,
      headers:{'Content-Type':'application/json', ...(csrf ? {'X-CSRFToken':csrf} : {})},
      body:body === undefined ? undefined : JSON.stringify(body)});
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw Object.assign(Error(data.message || data.error || 'Couldn’t reach the report inbox.'), {status:response.status});
    return data;
  } finally { clearTimeout(timer); }
}

function capture() {
  try {
    return copy({version:1, capturedAt:new Date().toISOString(),
      path:location.pathname+location.hash, title:document.title,
      details:adapter.snapshot?.() ?? {}, screenText:(adapter.screenText?.() ?? '').slice(0,12000),
      browser:{userAgent:navigator.userAgent, language:navigator.language, online:navigator.onLine,
        viewport:{width:innerWidth, height:innerHeight}}});
  } catch { return {path:location.pathname, details:{snapshotError:true}}; }
}

function showReport() {
  if (opened) return;
  // Retain UUID and context after cancel/network loss, including a lost 202 response.
  draft ??= {id:newId(), note:'', context:capture()};
  try { adapter.pause?.(); } catch { /* A broken player must not block reporting. */ }
  opened = true;
  const dialog = document.createElement('dialog');
  dialog.className = 'bug-report-dialog'; dialog.setAttribute('aria-labelledby','bug-report-title');
  dialog.innerHTML = '<form><h2 id="bug-report-title">Bug report</h2><label for="bug-report-note">What should we fix?</label><textarea id="bug-report-note" name="note" rows="4" maxlength="2000" required></textarea><p class="bug-report-status" role="status" aria-live="polite"></p><div class="bug-report-actions"><button type="button" data-history>Report history</button><button type="button" data-close>Cancel</button><button type="submit">File report</button></div></form>';
  document.body.append(dialog);
  const form = dialog.querySelector('form'), note = form.elements.note;
  const status = dialog.querySelector('[role=status]'), submit = form.querySelector('[type=submit]');
  const close = form.querySelector('[data-close]'), history = form.querySelector('[data-history]');
  history.hidden = adapter.history === false;
  note.value = draft.note;
  note.readOnly = !!draft.attempted;
  let sending = false, submitted = false;
  close.onclick = () => dialog.close();
  history.onclick = () => {dialog.addEventListener('close',showHistory,{once:true}); dialog.close();};
  dialog.addEventListener('cancel', event => { if (sending) event.preventDefault(); });
  dialog.addEventListener('close', () => {
    draft = submitted || !note.value.trim() ? null : {...draft, note:note.value};
    opened = false; dialog.remove();
  });
  form.onsubmit = async event => {
    event.preventDefault(); if (sending || submitted || !note.value.trim()) return;
    // Freeze the note after an attempted send too: an accepted-but-lost response
    // must be retried with exactly the original payload.
    if (!draft.attempted) draft.note = note.value.trim();
    draft.attempted = true; note.value = draft.note;
    note.readOnly = true;
    sending = true; submit.disabled = close.disabled = history.disabled = note.disabled = true;
    status.textContent = 'Filing report…';
    try {
      await request(endpoint(), {id:draft.id, note:draft.note, context:draft.context});
      submitted = true; status.textContent = 'Report filed. A fix is queued.';
      submit.hidden = true; close.disabled = history.disabled = false; close.textContent = 'Done';
    } catch (error) {
      if (error.status >= 400 && error.status < 500) {draft.attempted = false; note.readOnly = false;}
      status.textContent = error.status ? error.message+' Your note is still here.' : adapter.connectionHint ? adapter.connectionHint+' Your note is still here.' : navigator.onLine ? 'Couldn’t confirm the report. Your note is still here; retry when connected.' : 'You’re offline. Your note is still here; reconnect and retry.';
      submit.disabled = close.disabled = history.disabled = false;
      note.disabled = false;
      // A failed attempt remains retryable without creating another report.
    } finally { sending = false; }
  };
  dialog.showModal(); note.focus();
}

function element(tag, text, parent) {
  const node = document.createElement(tag); node.textContent = text; parent?.append(node); return node;
}

async function showHistory() {
  if (opened) return;
  opened = true;
  const dialog = document.createElement('dialog'); dialog.className = 'bug-report-dialog bug-report-history';
  dialog.setAttribute('aria-labelledby','report-history-title');
  dialog.innerHTML = '<h2 id="report-history-title">Bug reports</h2><p role="status" aria-live="polite"></p><div data-reports></div><div class="bug-report-actions"><button data-more hidden>Older reports</button><button data-close>Done</button></div>';
  document.body.append(dialog);
  const status = dialog.querySelector('[role=status]'), list = dialog.querySelector('[data-reports]'), more = dialog.querySelector('[data-more]');
  let next = null, older = false, busy = false;
  const render = report => {
    const row = element('article','',list); row.dataset.reportId = report.id;
    element('p', `${labels[report.status] || report.status} · ${new Date(report.created).toLocaleString()}`, row);
    element('p', report.note, row);
    if (report.result?.summary) element('p', report.result.summary, row);
    const detail = element('details','',row); element('summary','Details',detail);
    let loaded = false;
    detail.addEventListener('toggle', async () => {
      if (!detail.open || loaded) return;
      loaded = true;
        try { const data = await request(endpoint()+'/'+report.id); element('pre', JSON.stringify(data,null,2), detail); }
      catch { loaded = false; element('p','Couldn’t load details. Close and reopen to retry.',detail); }
    });
    if (['failed','needs_attention'].includes(report.status)) {
      const retry = element('button','Retry fix',row); retry.type = 'button';
      retry.onclick = async () => {
        retry.disabled = true;
        try { await request(endpoint()+'/'+report.id+'/retry',{}); status.textContent = 'Fix queued.'; await load(false); }
        catch (error) { status.textContent = error.message; retry.disabled = false; }
      };
    }
  };
  async function load(append) {
    if (busy) return;
    busy = true;
    try {
      const data = await request(endpoint()+(append && next ? '?before='+encodeURIComponent(next) : ''));
      if (!dialog.open) return;
      if (!append) list.replaceChildren();
      data.reports.forEach(render); next = data.next; more.hidden = !next;
      if (!list.childElementCount) status.textContent = 'No reports yet.';
    } catch (error) { status.textContent = error.message; }
    finally { busy = false; }
  }
  more.onclick = () => {older = true; load(true);};
  dialog.querySelector('[data-close]').onclick = () => dialog.close();
  const timer = setInterval(() => {
    if (!document.hidden && !older && !dialog.querySelector('details[open]')) load(false);
  },5000);
  dialog.addEventListener('close', () => {clearInterval(timer); opened = false; dialog.remove();});
  dialog.showModal(); await load(false);
}

export function registerBugReporter(value) {
  adapter = value;
  const button = document.createElement('button'); button.type = 'button';
  button.className = 'bug-report-button'; button.dataset.bugReport = '';
  button.setAttribute('aria-label','Bug report'); button.title = 'Bug report';
  button.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 8h8v8a4 4 0 0 1-8 0V8Zm1-3 1 3m5-3-1 3M4 10h4m8 0h4M4 15h4m8 0h4M5 21l4-3m6 0 4 3M12 9v9"/></svg><span>Bug report</span>';
  button.onclick = showReport;
  const target = document.querySelector(value.mount || 'nav');
  if (target) target.append(button);
  else {button.classList.add('bug-report-floating'); document.body.append(button);}
}
