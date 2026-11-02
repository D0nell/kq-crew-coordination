/* Reusable alerts-panel UI for the dedicated alerts page.
 * Provides: renderAlerts(), refreshAlerts(), selection, individual resolve,
 * bulk resolve, confirmation modal, feedback and automatic refresh.
 * Loaded after the minimal inline script in alerts.html (which defines $, state, api, ...). */
(function () {
  // Selection lives on the shared page state. It was never created before, so
  // select-all and every alert checkbox threw "Cannot read properties of undefined".
  state.selected = state.selected || new Set();

  // ---- one message area: errors (red) and confirmations (green) ----
  let msgKind = '';
  function showMsg(text, kind) {
    const b = $('alertMsg');
    msgKind = text ? (kind || 'error') : '';
    b.textContent = text || '';
    b.className = 'banner' + (msgKind === 'ok' ? ' ok' : '');
    b.hidden = !text;
  }

  // ---- alert rendering ----
  function renderAlerts(a) {
    const open = $('astatus').value === 'open';
    $('acount').textContent = `${a.count} ${open ? 'open' : 'resolved'}`;
    $('alerts').innerHTML = a.items.map((x) => `
      <li>
        <div class="a-top">${open ? `<input type="checkbox" class="alert-check" data-alert-id="${x.alert_id}" aria-label="Select alert for transit ${x.transit_id}">` : ''}${tag(x.severity)} <strong>${esc(x.corridor)}</strong></div>
        ${x.resolved ? '' : `<button data-resolve="${x.alert_id}" aria-label="Resolve alert for transit ${x.transit_id}">Resolve</button>`}
        <div class="a-meta">#${x.transit_id} · ${esc(x.rank)} to ${esc(x.destination)} · pickup ${fmtTime(x.scheduled_pickup_time)} · probability ${Number(x.delay_probability).toFixed(2)}</div>
      </li>`).join('');
    $('aempty').hidden = a.items.length > 0;
    $('aempty').innerHTML = state.search
      ? `<p>No ${open ? 'open' : 'resolved'} alerts match "${esc(state.search)}". Check the ID, or press Clear.</p>`
      : open
        ? '<p>No open alerts. Score transits in the queue to check them for delay risk.</p>'
        : '<p>No resolved alerts yet.</p>';
    syncSelection();
  }

  // Keeps ticks, the counter and "Select all" consistent with what is on screen.
  function syncSelection() {
    const open = $('astatus').value === 'open';
    const boxes = [...$('alerts').querySelectorAll('input.alert-check')];
    const present = new Set(boxes.map((cb) => Number(cb.dataset.alertId)));
    [...state.selected].forEach((id) => { if (!present.has(id)) state.selected.delete(id); });
    boxes.forEach((cb) => { cb.checked = state.selected.has(Number(cb.dataset.alertId)); });
    $('selectAll').disabled = !open || boxes.length === 0;
    $('selectAll').checked = boxes.length > 0 && boxes.every((cb) => cb.checked);
    $('resolveSelected').textContent = `Resolve selected ${state.selected.size}`;
    $('resolveSelected').disabled = state.selected.size === 0;
  }

  // ---- alerts fetch + render (also the auto-refresh cycle) ----
  async function refreshAlerts() {
    state._busy = true;
    const mySeq = state._reqSeq = (state._reqSeq || 0) + 1;
    $('alerts').setAttribute('aria-busy', 'true');
    try {
      const a = await api('/api/alerts?status=' + $('astatus').value);
      if (mySeq !== state._reqSeq) return; // a newer request (e.g. a filter change) superseded this one
      state.__alerts = a.items;
      const term = state.search;
      // Exact-ID match on transit or alert number; filtered here so it works for every row loaded.
      const shown = term ? a.items.filter((x) => String(x.transit_id) === term.replace(/^#/, '') || String(x.alert_id) === term.replace(/^#/, '')) : a.items;
      $('searchNote').textContent = term ? `${shown.length} match${shown.length === 1 ? '' : 'es'} for "${term}"` : '';
      renderAlerts({ count: shown.length, items: shown });
      if (msgKind === 'error') showMsg(''); // a successful refresh clears an old error, never a confirmation
      setUpdatedTimestamp('Last updated ' + new Date().toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }));
    } catch (e) { if (mySeq === state._reqSeq) showMsg(e.message, 'error'); }
    finally {
      if (mySeq === state._reqSeq) { state._busy = false; $('alerts').setAttribute('aria-busy', 'false'); }
    }
  }

  // ---- search (separate from the filter; matches transit ID or alert ID) ----
  state.search = '';
  $('searchForm').addEventListener('submit', (e) => {
    e.preventDefault();
    state.search = $('search').value.trim();
    $('searchClear').hidden = !state.search;
    refreshAlerts();
  });
  $('searchClear').addEventListener('click', () => {
    $('search').value = ''; state.search = ''; $('searchClear').hidden = true;
    refreshAlerts(); $('search').focus();
  });

  // ---- filter ----
  $('astatus').addEventListener('change', () => {
    state.selected.clear();
    showMsg('');
    refreshAlerts();
  });

  // ---- alert selection + bulk resolution ----
  $('selectAll').addEventListener('change', () => {
    const on = $('selectAll').checked;
    $('alerts').querySelectorAll('input.alert-check').forEach((cb) => {
      const id = Number(cb.dataset.alertId);
      if (on) state.selected.add(id); else state.selected.delete(id);
    });
    syncSelection();
  });

  $('alerts').addEventListener('change', (e) => {
    const cb = e.target.closest('input.alert-check');
    if (!cb) return;
    const id = Number(cb.dataset.alertId);
    if (cb.checked) state.selected.add(id); else state.selected.delete(id);
    syncSelection();
  });

  $('resolveSelected').addEventListener('click', function () {
    if (state.selected.size === 0) return;
    openConfirmModal(this);
  });

  $('confirmCancel').addEventListener('click', closeConfirmModal);

  $('confirmOk').addEventListener('click', async () => {
    const ids = [...state.selected];
    if (ids.length === 0) { closeConfirmModal(); return; }
    $('confirmOk').disabled = true;
    showMsg('');
    try {
      const result = await api('/api/alerts/bulk-resolve', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ alert_ids: ids }),
      });
      state.selected.clear();
      closeConfirmModal();
      await refreshAlerts();
      const c = result.counts || {};
      const parts = [];
      if (c.resolved) parts.push(`Resolved ${c.resolved} alert${c.resolved === 1 ? '' : 's'} (${c.resolved} of ${c.total}).`);
      if (c.already_resolved) parts.push(`${c.already_resolved} were already resolved.`);
      if (c.not_found) parts.push(`${c.not_found} id${c.not_found === 1 ? ' is' : 's are'} not found.`);
      if (c.ineligible) parts.push(`${c.ineligible} is/are not eligible (non-model alert).`);
      if (c.failed) parts.push(`${c.failed} caused a server-side failure.`);
      const unresolved = [...(result.not_found_alert_ids || []), ...(result.ineligible_alert_ids || []), ...(result.failed_alert_ids || [])];
      if (unresolved.length) parts.push('Not resolved: ' + unresolved.join(', '));
      const problem = c.not_found || c.ineligible || c.failed;
      showMsg(parts.join(' ') || 'No alerts were changed.', problem ? 'error' : 'ok');
    } catch (err) {
      closeConfirmModal();           // the error must not hide behind the overlay
      showMsg(err.message, 'error');
    } finally {
      $('confirmOk').disabled = false;
    }
  });

  // ---- individual resolve (shows "resolved" only after the server confirms) ----
  document.addEventListener('click', async (e) => {
    const b = e.target.closest('button[data-resolve]'); if (!b) return;
    b.disabled = true;
    try {
      await api(`/api/alerts/${b.dataset.resolve}/resolve`, { method: 'PATCH' });
      state.selected.delete(Number(b.dataset.resolve));
      await refreshAlerts();
      showMsg('Alert resolved.', 'ok');
    } catch (err) {
      b.disabled = false;
      showMsg(err.message, 'error');
    }
  });

  // ---- modal focus management ----
  const confirmModal = $('confirmModal');
  let modalFocusTarget = null;

  function openConfirmModal(source) {
    modalFocusTarget = source;
    const n = state.selected.size;
    $('confirmModalText').textContent = `Confirm resolution of ${n} selected alert${n === 1 ? '' : 's'}?`;
    confirmModal.hidden = false;
    const first = confirmModal.querySelector('button');
    if (first) first.focus();
  }

  function closeConfirmModal() {
    confirmModal.hidden = true;
    if (modalFocusTarget && typeof modalFocusTarget.focus === 'function') {
      modalFocusTarget.focus();
    }
  }

  // Keyboard: Escape closes the modal; Tab cycles focus within the modal.
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') {
      if (!confirmModal.hidden) closeConfirmModal();
      return;
    }
    if (e.key !== 'Tab' || confirmModal.hidden) return;
    const focusable = confirmModal.querySelectorAll('button:not(:disabled)');
    if (focusable.length === 0) return;
    let idx = Array.prototype.indexOf.call(focusable, document.activeElement); // was const: reassigning it threw
    if (e.shiftKey) {
      if (idx <= 0) idx = focusable.length - 1;
      else idx -= 1;
    } else {
      if (idx >= focusable.length - 1) idx = 0;
      else idx += 1;
    }
    e.preventDefault();
    focusable[idx].focus();
  });

  // ---- automatic alerts refresh ----
  const REFRESH_MS = 15000;
  let autoTimer = null;

  // Defined at this level (it used to be defined inside a nested function, so the
  // export below failed with "startAutoRefresh is not defined" and nothing ever loaded).
  function startAutoRefresh(initial) {
    if (autoTimer) { clearInterval(autoTimer); autoTimer = null; }
    if (initial && !state._busy) { refreshAlerts().catch(() => {}); }
    autoTimer = setInterval(() => {
      if (state._busy) return;
      refreshAlerts().catch(() => {});
    }, REFRESH_MS);
  }

  function handleVisibilityChange() {
    if (document.hidden) {
      if (autoTimer) { clearInterval(autoTimer); autoTimer = null; }
      return;
    }
    startAutoRefresh(true);
  }

  document.addEventListener('visibilitychange', handleVisibilityChange);
  // The page's inline script calls this once the shared globals (api, state, $, ...) exist.
  window.__kqAlerts = window.__kqAlerts || {};
  window.__kqAlerts.startAutoRefresh = startAutoRefresh;
  window.__kqAlerts.refreshAlerts = refreshAlerts;
})();