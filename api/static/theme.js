/* Shared theme logic for Dashboard, What-if Prediction and Alerts pages.
 * One preference, stored in localStorage['kq.theme']: 'system' | 'light' | 'dark'.
 * kq.css gates its colour variables on :root[data-theme="..."] and, when no
 * data-theme attribute is present (System mode), on prefers-color-scheme, so
 * System follows the operating system live with no JavaScript.
 *
 * This file starts itself. It does NOT depend on a page script reaching an
 * initTheme() call at the end of its inline script: if that script throws
 * earlier, the theme still works. Calling initTheme() again is harmless. */
(function () {
  const THEME_KEY = 'kq.theme';
  const THEME_ORDER = ['system', 'light', 'dark'];
  const THEME_NAMES = { system: 'System', light: 'Light', dark: 'Dark' };
  // Icon shapes only. Colour comes from CSS (stroke: currentColor), so the
  // icons follow the button's text colour in every theme.
  const THEME_ICONS = {
    system: '<rect x="2" y="4" width="20" height="14" rx="2"/><path d="M8 21h8M12 18v3"/>',
    light: '<circle cx="12" cy="12" r="4.5"/><path d="M12 2.8v3.2M12 18v3.2M3 12h3.2M18 12h3.2M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M18.4 5.6l-2.1 2.1M7.7 16.3l-2.1 2.1"/>',
    dark: '<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/>'
  };

  function storedTheme() {
    try {
      const v = localStorage.getItem(THEME_KEY);
      return v === 'light' || v === 'dark' || v === 'system' ? v : 'system';
    } catch (e) { return 'system'; }
  }

  function applyTheme(theme) {
    const root = document.documentElement;
    if (theme === 'light' || theme === 'dark') root.setAttribute('data-theme', theme);
    else root.removeAttribute('data-theme'); // System: let prefers-color-scheme decide
  }

  function nextTheme(current) {
    return THEME_ORDER[(THEME_ORDER.indexOf(current) + 1) % THEME_ORDER.length];
  }

  // The icon shows the SELECTED mode (System keeps the monitor icon even when the OS is dark).
  function syncThemeControl(theme) {
    const btn = document.getElementById('themeBtn');
    if (!btn) return;
    const icon = btn.querySelector('svg.icon');
    if (icon) {
      icon.setAttribute('fill', 'none');
      icon.innerHTML = THEME_ICONS[theme];
    }
    const text = THEME_NAMES[theme] + ' theme. Click to switch to ' + THEME_NAMES[nextTheme(theme)] + '.';
    btn.setAttribute('aria-label', text);
    btn.setAttribute('title', text);
  }

  let wired = false;
  function initTheme() {
    const theme = storedTheme();
    applyTheme(theme);
    syncThemeControl(theme);
    const btn = document.getElementById('themeBtn');
    if (btn && !wired) {
      wired = true; // one click handler only, however many times initTheme() runs
      btn.addEventListener('click', function () {
        const next = nextTheme(storedTheme());
        try { localStorage.setItem(THEME_KEY, next); } catch (e) { /* storage blocked: still switch for this page */ }
        applyTheme(next);
        syncThemeControl(next);
      });
    }
  }

  applyTheme(storedTheme()); // apply as early as this script runs
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initTheme);
  else initTheme();

  window.__kqTheme = { initTheme: initTheme };
})();