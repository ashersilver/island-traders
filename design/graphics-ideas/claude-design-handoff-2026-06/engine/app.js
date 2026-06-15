/* ============================================================
   app.js — orchestration, camera, render loop, UI wiring
   ============================================================ */
(function (global) {
  'use strict';
  const Iso = global.Iso, Island = global.Island, Seasons = global.Seasons,
        Crops = global.Crops;

  const SCENE_W = 860, SCENE_H = 560;
  const ZOOM = 1.06;
  const STORE_KEY = 'island_traders_v1';

  const state = {
    island: 'farmer',
    season: 'summer',
    weather: 'normal',
    built: {},          // itemId -> bool
    fields: {},         // fieldId -> bool
    showWater: true,
    autoSeason: false,
  };

  let canvas, ctx, dpr = 1, view = { s: 1, ox: 0, oy: 0, cw: 0, ch: 0 };
  let particles = Seasons.makeParticles();
  let last = 0;

  // ---- init defaults from island data --------------------------------
  function islandDef() { return global.ISLANDS[state.island]; }

  function seedDefaults() {
    const def = islandDef();
    def.items.forEach(it => { if (!(it.id in state.built)) state.built[it.id] = !!it.mandatory; });
    def.fields.forEach(f => { if (!(f.id in state.fields)) state.fields[f.id] = !!f.on; });
  }

  function save() {
    try { localStorage.setItem(STORE_KEY, JSON.stringify({ season: state.season, weather: state.weather, built: state.built, fields: state.fields })); } catch (e) {}
  }
  function load() {
    try {
      const s = JSON.parse(localStorage.getItem(STORE_KEY) || '{}');
      if (s.season) state.season = s.season;
      if (s.weather) state.weather = s.weather;
      if (s.built) state.built = s.built;
      if (s.fields) state.fields = s.fields;
    } catch (e) {}
  }

  // ---- camera --------------------------------------------------------
  function resize() {
    const wrap = canvas.parentElement;
    const cw = wrap.clientWidth, ch = wrap.clientHeight;
    dpr = Math.min(2, global.devicePixelRatio || 1);
    canvas.width = cw * dpr; canvas.height = ch * dpr;
    canvas.style.width = cw + 'px'; canvas.style.height = ch + 'px';
    const s = Math.min(cw / SCENE_W, ch / SCENE_H) * ZOOM;
    view = { s, ox: cw / 2, oy: ch * 0.52, cw, ch };
  }

  // ---- water ---------------------------------------------------------
  function drawWater(pal, t) {
    ctx.save();
    ctx.beginPath();
    rrect(ctx, -SCENE_W / 2 - 40, -SCENE_H / 2, SCENE_W + 80, SCENE_H + 40, 60);
    const g = ctx.createLinearGradient(0, -SCENE_H / 2, 0, SCENE_H / 2);
    g.addColorStop(0, Iso.shade(pal.waterDeep, 0.10));
    g.addColorStop(0.5, pal.waterDeep);
    g.addColorStop(1, Iso.shade(pal.waterDeep, -0.16));
    ctx.fillStyle = g; ctx.fill();
    ctx.clip();
    // shimmer bands
    ctx.strokeStyle = Iso.withAlpha(pal.waterShallow, 0.30); ctx.lineWidth = 2;
    for (let y = -SCENE_H / 2; y < SCENE_H / 2; y += 22) {
      ctx.beginPath();
      for (let x = -SCENE_W / 2 - 40; x < SCENE_W / 2 + 40; x += 24) {
        const yy = y + Math.sin((x + t * 0.02) / 40) * 3 + Math.sin((x - t * 0.01) / 18) * 1.5;
        if (x === -SCENE_W / 2 - 40) ctx.moveTo(x, yy); else ctx.lineTo(x, yy);
      }
      ctx.stroke();
    }
    // sparkle highlights
    ctx.fillStyle = Iso.withAlpha('#eaf6f6', 0.16);
    const rng = Iso.makeRNG(99);
    for (let i = 0; i < 60; i++) {
      const x = (rng() - 0.5) * SCENE_W, y = (rng() - 0.5) * SCENE_H;
      const tw = 0.5 + 0.5 * Math.sin(t / 400 + i);
      ctx.globalAlpha = 0.10 + 0.12 * tw;
      ctx.fillRect(x, y + Math.sin(t / 600 + i) * 2, 3, 1);
    }
    ctx.globalAlpha = 1;
    ctx.restore();
  }

  function rrect(ctx, x, y, w, h, r) {
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y, x + w, y + h, r);
    ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r);
    ctx.arcTo(x, y, x + w, y, r);
    ctx.closePath();
  }

  // ---- main render ---------------------------------------------------
  let geo = null;
  function rebuildGeo() { geo = Island.generate(islandDef().shape.seed, islandDef().shape); }

  function render(t) {
    const dt = Math.min(40, t - last); last = t;
    const def = islandDef();
    const resolved = Seasons.resolve(state.season, state.weather);
    const pal = resolved.pal;
    const flags = resolved.flags;
    // Apply island-specific palette tweaks (e.g. rocky grass for miner)
    if (def.paletteOverride) def.paletteOverride(pal);

    // sky backdrop (screen space)
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const sky = ctx.createLinearGradient(0, 0, 0, view.ch);
    sky.addColorStop(0, pal.sky); sky.addColorStop(1, pal.skyLow);
    ctx.fillStyle = sky; ctx.fillRect(0, 0, view.cw, view.ch);

    // world transform
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.translate(view.ox, view.oy); ctx.scale(view.s, view.s);

    if (state.showWater) drawWater(pal, t);

    // terrain
    Island.drawBase(ctx, geo, pal, flags, t);

    // collect objects — start with scenery, then add fields + items
    let list = def.scenery(pal, flags, t);

    // active fields (ground decals + any field-specific objects like cattle)
    def.fields.forEach(f => {
      if (!state.fields[f.id]) return;
      Crops.drawField(ctx, f.field, pal, flags, t);
      // cattle on pasture only if livestock barn is also built
      if (f.parts && state.built['farmer.livestock_barn']) {
        list = list.concat(f.parts(pal, flags, t));
      }
    });

    def.items.forEach(it => {
      if (state.built[it.id]) list = list.concat(it.parts(pal, flags, t));
    });
    list.sort((a, b) => a.depth - b.depth);
    for (const o of list) { ctx.save(); o.fn(ctx, t); ctx.restore(); }

    // flood water over land + shoreline
    Island.drawFlood(ctx, geo, pal, flags, t);
    Island.drawShoreFoam(ctx, geo, pal, flags, t);

    // ambient light tint over the whole scene
    if (pal.ambientA > 0) {
      ctx.fillStyle = Iso.withAlpha(pal.ambient.replace('1)', pal.ambientA + ')').replace('rgba', 'rgba'), 1);
      ctx.globalCompositeOperation = 'soft-light';
      ctx.fillStyle = solidAmbient(pal);
      ctx.fillRect(-SCENE_W, -SCENE_H, SCENE_W * 2, SCENE_H * 2);
      ctx.globalCompositeOperation = 'source-over';
    }

    // particles (screen space)
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    particles.update(flags, t, view.cw, view.ch, dt);
    particles.drawFront(ctx, flags, pal, t, view.cw, view.ch);

    requestAnimationFrame(render);
  }

  function solidAmbient(pal) {
    // build rgba with alpha from ambient string
    const m = pal.ambient.match(/rgba?\(([^)]+)\)/);
    if (!m) return 'rgba(0,0,0,0)';
    const parts = m[1].split(',').map(s => s.trim());
    return `rgba(${parts[0]},${parts[1]},${parts[2]},${pal.ambientA})`;
  }

  // ---- UI ------------------------------------------------------------
  function buildUI() {
    // season + weather segmented
    document.querySelectorAll('[data-season]').forEach(b => b.addEventListener('click', () => {
      state.season = b.dataset.season; syncSeg(); save();
    }));
    document.querySelectorAll('[data-weather]').forEach(b => b.addEventListener('click', () => {
      state.weather = b.dataset.weather; syncSeg(); save();
    }));
    document.querySelectorAll('[data-island]').forEach(b => b.addEventListener('click', () => {
      switchIsland(b.dataset.island);
    }));
    renderBuildPanel();
    syncSeg();
  }

  function syncSeg() {
    document.querySelectorAll('[data-season]').forEach(b => b.classList.toggle('on', b.dataset.season === state.season));
    document.querySelectorAll('[data-weather]').forEach(b => b.classList.toggle('on', b.dataset.weather === state.weather));
    document.querySelectorAll('[data-island]').forEach(b => b.classList.toggle('on', b.dataset.island === state.island));
    const def = islandDef();
    document.getElementById('island-name').textContent = def.name;
    document.getElementById('island-tag').textContent = def.tagline;
    const pillEl = document.getElementById('island-pill');
    if (pillEl) pillEl.textContent = def.pill || def.name;
    updateStats();
  }

  // ---- island switching -------------------------------------------
  function switchIsland(id) {
    state.island = id;
    state.built = {};
    state.fields = {};
    seedDefaults();
    rebuildGeo();
    renderBuildPanel();
    syncSeg();
    save();
  }

  // Cosmetic but plausible headline figures driven by season/weather/build.
  function updateStats() {
    const { flags } = Seasons.resolve(state.season, state.weather);
    const b = state.built, fld = state.fields;
    const droughtCut = flags.drought ? 0.6 : 1;
    const floodCut  = flags.flood  ? 0.7 : 1;
    const winterCut = flags.bare   ? 0.5 : 1;
    const envCut = droughtCut * floodCut * winterCut;

    setChip('stat-season',  (Seasons.SEASONS[state.season]  || {}).label || state.season);
    setChip('stat-weather', (Seasons.WEATHER[state.weather] || {}).label || state.weather);
    const wEl = document.getElementById('stat-weather');
    if (wEl) wEl.className = 'chip-v ' + (state.weather === 'drought' ? 'warn' : state.weather === 'flood' ? 'bad' : 'ok');

    if (state.island === 'farmer') {
      const harvestBoost = flags.cropStage != null ? (0.6 + flags.cropStage * 0.8) : 1;
      let grain   = ((fld['land.grain'] ? 10 : 0) + (b['farmer.tractor'] ? 10 : 0) + (b['farmer.harvester'] ? 6 : 0)) * harvestBoost * envCut;
      let produce = ((fld['land.veg'] ? 6 : 0) + (b['farmer.tractor'] ? 6 : 0) + (fld['land.orchard'] ? 4 : 0)) * harvestBoost * envCut;
      let fish    = (b['farmer.fishing_boat'] ? 4 : 0) * ((flags.fishRun == null ? 1 : flags.fishRun) * 2.5);
      let meat    = (b['farmer.livestock_barn'] ? 4 : 0);
      const food  = Math.min(grain||0, produce||0, (fish||meat)||1) + (b['farmer.industrial_kitchen'] ? 6 : 0) + (b['common.kitchen'] ? 6 : 0);
      showChips(['stat-food','stat-grain','stat-fish','stat-meat']);
      hideChips(['stat-ore','stat-oil','stat-metal','stat-cargo','stat-marine','stat-land','stat-express']);
      setChip('stat-food',  Math.round(food));
      setChip('stat-grain', Math.round(grain));
      setChip('stat-fish',  Math.round(fish));
      setChip('stat-meat',  Math.round(meat));
    } else if (state.island === 'miner') {
      let ore   = ((b['miner.excavator'] ? 40 : 0) + (b['miner.crusher'] ? 20 : 0)) * envCut;
      let oil   = ((b['miner.oil_rig']  ? 40 : 0) + (b['miner.refinery'] ? 20 : 0)) * envCut;
      let metal = ((b['miner.crusher'] ? 20 : 0)  + (b['miner.enhanced_crusher_smelter'] ? 60 : 0)) * envCut;
      showChips(['stat-ore','stat-oil','stat-metal']);
      hideChips(['stat-food','stat-grain','stat-fish','stat-meat','stat-cargo','stat-marine','stat-land','stat-express']);
      setChip('stat-ore',   Math.round(ore));
      setChip('stat-oil',   Math.round(oil));
      setChip('stat-metal', Math.round(metal));
    } else if (state.island === 'transporter') {
      const cargo   = ((b['transport.container_terminal'] ? 40 : 0) + (b['transport.cargo_crane'] ? 20 : 0) + (b['transport.freight_depot'] ? 20 : 0) + (b['transport.refrigerated_warehouse'] ? 15 : 0)) * envCut;
      const marine  = ((b['transport.container_terminal'] ? 10 : 0) + (b['transport.cargo_crane'] ? 10 : 0) + (b['transport.tugboat'] ? 20 : 0)) * envCut;
      const land    = ((b['transport.truck_fleet'] ? 25 : 0) + (b['transport.freight_depot'] ? 10 : 0)) * envCut;
      const express = (b['transport.air_cargo'] ? 15 : 0);
      showChips(['stat-cargo','stat-marine','stat-land','stat-express']);
      hideChips(['stat-food','stat-grain','stat-fish','stat-meat','stat-ore','stat-oil','stat-metal']);
      setChip('stat-cargo',   Math.round(cargo));
      setChip('stat-marine',  Math.round(marine));
      setChip('stat-land',    Math.round(land));
      setChip('stat-express', Math.round(express));
    }
  }
  function setChip(id, v) { const el = document.getElementById(id); if (el) el.textContent = v; }
  function showChips(ids) { ids.forEach(id => { const el = document.getElementById(id + '-chip'); if (el) el.style.display = ''; }); }
  function hideChips(ids) { ids.forEach(id => { const el = document.getElementById(id + '-chip'); if (el) el.style.display = 'none'; }); }

  function renderBuildPanel() {
    const def = islandDef();
    const host = document.getElementById('build-list');
    host.innerHTML = '';
    const groups = {};
    def.fields.forEach(f => { (groups[f.group] = groups[f.group] || []).push({ kind: 'field', it: f }); });
    def.items.forEach(it => { (groups[it.group] = groups[it.group] || []).push({ kind: 'item', it }); });
    const order = ['Capital equipment', 'Land & livestock'];
    order.forEach(gname => {
      if (!groups[gname]) return;
      const h = document.createElement('div'); h.className = 'group-h'; h.textContent = gname; host.appendChild(h);
      groups[gname].forEach(({ kind, it }) => {
        const on = kind === 'field' ? state.fields[it.id] : state.built[it.id];
        const row = document.createElement('button');
        row.className = 'build-row' + (on ? ' on' : '');
        row.innerHTML =
          `<span class="chk" aria-hidden="true"></span>
           <span class="bi"><span class="bn">${it.name}${it.mandatory ? '<em class="req">Required</em>' : ''}</span>
           <span class="bd">${it.desc || (it.field ? 'Productive land' : '')}</span></span>
           <span class="bc">${it.cost ? it.cost + ' Dp' : ''}</span>`;
        row.addEventListener('click', () => {
          if (kind === 'field') state.fields[it.id] = !state.fields[it.id];
          else state.built[it.id] = !state.built[it.id];
          row.classList.toggle('on');
          updateStats();
          save();
        });
        host.appendChild(row);
      });
    });
  }

  // ---- boot ----------------------------------------------------------
  function init() {
    canvas = document.getElementById('stage');
    ctx = canvas.getContext('2d');
    load(); seedDefaults(); rebuildGeo();
    resize(); buildUI();
    global.addEventListener('resize', resize);
    requestAnimationFrame(render);
    // expose for tweaks
    global.__island = { state, save, renderBuildPanel, syncSeg, switchIsland };
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})(window);
