/* minimal dispatcher crew-location map (FR-10).
 * Draws a Leaflet map of crew pings from GET /api/crew-locations and a matching
 * location list. Marker colour = status (in-transit / arrived / no-location). */
(function () {
  'use strict';

  const $ = (id) => document.getElementById(id);

  // colour per status (mirrors the design-system tokens used by the rest of the app)
  const STATUS = { true: 'in-transit', false: 'arrived', null: 'no-location' };
  const COLORS = { 'in-transit': '#1f4fd8', arrived: '#17673a', 'no-location': '#5f6b7a' };
  const TICK_MS = 15000; // re-fetch locations every 15s so the map stays live

  function esc(s) {
    return String(s ?? '').replace(/[&<>"']/g, (c) => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[c]));
  }

  function fmt(ts) {
    try { return new Date(ts).toLocaleString([], { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }); }
    catch (e) { return String(ts ?? ''); }
  }

  // Build a Leaflet marker whose colour encodes the transit state.
  function makeIcon(arrived) {
    const color = COLORS[arrived ? 'arrived' : 'in-transit'];
    return L.divIcon({
      className: 'kq-pin',
      html: '<div class="kq-pin" style="background:' + color + '"></div>',
      iconSize: [16, 16], iconAnchor: [8, 8],
    });
  }

  function renderList(items) {
    const list = $('locList');
    const empty = $('emptyLoc');
    if (!items.length) { list.innerHTML = ''; empty.hidden = false; return; }
    empty.hidden = true;
    list.innerHTML = items.map((it) => `
      <li class="loc-row">
        <span class="loc-dot loc-icon" style="background:${COLORS[it.arrived ? 'arrived' : 'in-transit']}"></span>
        <div class="loc-info">
          <div class="loc-name">${esc(it.crew_name || '—')}</div>
          <div class="loc-sub">${esc(it.corridor)}${it.arrived ? ' &middot; arrived' : ' &middot; in transit'}</div>
        </div>
        <span class="loc-status">${STATUS[it.arrived]}</span>
      </li>
    `).join('');
  }

  function reCenterOn(marker, lat, lon) {
    MAP.map.setView([lat, lon], 13, { animate: true });
    marker.openPopup();
  }

  async function loadLocations() {
    try {
      const resp = await fetch('/api/crew-locations');
      if (!resp.ok) { renderList([]); return; }
      const data = await resp.json();
      renderList(data.items);

      const group = L.layerGroup();
      MAP.items = [];
      for (const it of data.items) {
        const marker = L.marker([it.latitude, it.longitude], { icon: makeIcon(!!it.arrived) })
          .bindPopup(`
            <div class="kv"><span>Transit</span><strong>${esc(it.transit_id)}</strong></div>
            <div class="kv"><span>Crew</span><strong>${esc(it.crew_name || '—')}</strong></div>
            <div class="kv"><span>Corridor</span><strong>${esc(it.corridor)}</strong></div>
            <div class="kv"><span>Status</span><span class="loc-status">${STATUS[it.arrived]}</span></div>
            <div class="kv"><span>Reported</span><strong>${fmt(it.recorded_at)}</strong></div>
          `)
          .on('click', () => reCenterOn(marker, it.latitude, it.longitude));
        group.addLayer(marker);
        MAP.items.push({ marker, ...it });
      }
      MAP.layer = group; // replace the layer so we can re-draw on refresh
      MAP.map.addLayer(group);
    } catch (e) { renderList([]); }
  }

  // Build the map once on first load.
  async function init() {
    const map = L.map('map', { worldCopyJump: true, zoomControl: true }).setView([0.023, 36.823], 12);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: '&copy; <a href="https://openstreetmap.org">OpenStreetMap</a> contributors',
    }).addTo(map);

    // re-draw the layers on each tick (keeps the panel and the markers in sync)
    const tick = () => { MAP.layer = L.layerGroup(); loadLocations(); };

    MAP.map = map;
    loadLocations();
    setInterval(tick, TICK_MS);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init, { once: true });
  } else {
    init();
  }
})();
