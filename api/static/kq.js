/* Shared by every page: shows real system status from GET /health. No values are invented. */
(function () {
  var chip = document.getElementById('sysStatus');
  if (!chip) return;
  var DOT = '<svg viewBox="0 0 10 10" aria-hidden="true"><circle cx="5" cy="5" r="4.5"/></svg>';
  var SQ = '<svg viewBox="0 0 10 10" aria-hidden="true"><rect x=".5" y=".5" width="9" height="9"/></svg>';
  var TRI = '<svg viewBox="0 0 10 10" aria-hidden="true"><path d="M5 0 10 10H0z"/></svg>';
  function set(cls, icon, text) { chip.className = 'status ' + cls; chip.innerHTML = icon + text; }
  async function check() {
    try {
      var r = await fetch('/health');
      var h = await r.json();
      if (h.status === 'ok') set('ok', DOT, 'System ready');
      else if (h.database !== 'ok') set('warn', SQ, 'Database unreachable');
      else if (!h.model_file_found) set('warn', SQ, 'Model file not found');
      else set('warn', SQ, 'System degraded');
    } catch (e) { set('down', TRI, 'API unreachable'); }
  }
  check(); setInterval(check, 30000);
})();
