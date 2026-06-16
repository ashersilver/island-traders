/* ============================================================
   sprites.js — Building & prop draw functions (isometric)
   Each: fn(ctx, gx, gy, pal, opt, t). Drawn at ground (gx,gy).
   ============================================================ */
(function (global) {
  'use strict';
  const I = global.Iso;
  const { project, shade, mix, withAlpha, poly, isoBox, isoRoof, gableRoof, isoCylinder, blob } = I;
  const H = global.Island ? global.Island.LANDH : 24;
  const TILE = I.ISO.TILE, QUART = I.ISO.QUART;

  // window squares on a wall row, helper
  function windows(ctx, baseScreen, n, pal, lit) {
    // draw small glowing squares — baseScreen is a {x,y}
  }

  // ---- natural: deciduous tree --------------------------------------
  function tree(ctx, gx, gy, pal, opt) {
    opt = opt || {}; const s = opt.scale || 1; const fl = opt.flags || {};
    blob(ctx, gx, gy, 0.5 * s, H, 0.16);
    const trunkC = pal.trunk;
    // trunk
    isoBox(ctx, gx, gy, 0.16 * s, 0.16 * s, 16 * s, H, trunkC);
    const cx = project(gx, gy, H + 16 * s);
    const leaf = fl.bare ? mix(pal.leaf, '#8a8f86', 0.5) : pal.leaf;
    const leafD = pal.leafDark;
    if (fl.bare) {
      // bare branches
      ctx.save(); ctx.strokeStyle = trunkC; ctx.lineWidth = 2;
      for (let i = 0; i < 6; i++) { const a = (i / 6) * Math.PI * 2; ctx.beginPath(); ctx.moveTo(cx.x, cx.y); ctx.lineTo(cx.x + Math.cos(a) * 10 * s, cx.y - 8 * s + Math.sin(a) * 5 * s); ctx.stroke(); }
      ctx.restore();
      // light snow puff
      if (fl.snow) { ctx.beginPath(); ctx.ellipse(cx.x, cx.y - 6 * s, 14 * s, 9 * s, 0, 0, Math.PI * 2); ctx.fillStyle = 'rgba(238,243,244,0.65)'; ctx.fill(); }
      return;
    }
    // canopy: 3 overlapping blobs
    const puffs = [[0, -6, 18], [-9, 0, 13], [9, -1, 12], [0, 4, 14]];
    for (const [dx, dy, r] of puffs) {
      ctx.beginPath(); ctx.ellipse(cx.x + dx * s, cx.y + dy * s, r * s, r * 0.78 * s, 0, 0, Math.PI * 2);
      ctx.fillStyle = leafD; ctx.fill();
    }
    for (const [dx, dy, r] of puffs) {
      ctx.beginPath(); ctx.ellipse(cx.x + dx * s - 2, cx.y + dy * s - 3 * s, r * 0.82 * s, r * 0.62 * s, 0, 0, Math.PI * 2);
      ctx.fillStyle = leaf; ctx.fill();
    }
    if (opt.blossom && fl.blossom) {
      for (let i = 0; i < 10; i++) { const a = Math.random() * 6.28; ctx.beginPath(); ctx.arc(cx.x + Math.cos(a) * 12 * s, cx.y - 4 * s + Math.sin(a) * 9 * s, 1.4 * s, 0, 6.28); ctx.fillStyle = 'rgba(245,210,222,0.9)'; ctx.fill(); }
    }
    if (fl.snow) { ctx.beginPath(); ctx.ellipse(cx.x, cx.y - 8 * s, 15 * s, 8 * s, 0, 0, Math.PI * 2); ctx.fillStyle = 'rgba(240,245,246,0.55)'; ctx.fill(); }
  }

  // ---- natural: conifer ---------------------------------------------
  function pine(ctx, gx, gy, pal, opt) {
    opt = opt || {}; const s = opt.scale || 1; const fl = opt.flags || {};
    blob(ctx, gx, gy, 0.4 * s, H, 0.16);
    isoBox(ctx, gx, gy, 0.14 * s, 0.14 * s, 8 * s, H, pal.trunk);
    const base = project(gx, gy, H + 6 * s);
    const green = fl.snow ? mix(pal.leafDark, '#3a5230', 0.4) : pal.leafDark;
    const tiers = [[0, 20], [6, 26], [13, 30]];
    for (let i = tiers.length - 1; i >= 0; i--) {
      const [lift, w] = tiers[i];
      const yy = base.y - lift * s;
      poly(ctx, [{ x: base.x, y: yy - 16 * s }, { x: base.x - w * 0.5 * s, y: yy }, { x: base.x + w * 0.5 * s, y: yy }], i % 2 ? green : shade(green, 0.06));
      if (fl.snow) poly(ctx, [{ x: base.x, y: yy - 16 * s }, { x: base.x - w * 0.32 * s, y: yy - 6 * s }, { x: base.x + w * 0.32 * s, y: yy - 6 * s }], 'rgba(240,245,246,0.7)');
    }
  }

  // ---- natural: bush -------------------------------------------------
  function bush(ctx, gx, gy, pal, opt) {
    opt = opt || {}; const s = opt.scale || 1; const fl = opt.flags || {};
    const c = project(gx, gy, H);
    const leaf = fl.bare ? mix(pal.leaf, '#9aa090', 0.5) : pal.leaf;
    for (const [dx, dy, r] of [[-5, 0, 8], [5, 0, 8], [0, -3, 9]]) {
      ctx.beginPath(); ctx.ellipse(c.x + dx * s, c.y - 4 * s + dy * s, r * s, r * 0.7 * s, 0, 0, Math.PI * 2);
      ctx.fillStyle = pal.leafDark; ctx.fill();
      ctx.beginPath(); ctx.ellipse(c.x + dx * s, c.y - 6 * s + dy * s, r * 0.8 * s, r * 0.55 * s, 0, 0, Math.PI * 2);
      ctx.fillStyle = leaf; ctx.fill();
    }
    if (fl.snow) { ctx.beginPath(); ctx.ellipse(c.x, c.y - 9 * s, 10 * s, 5 * s, 0, 0, Math.PI * 2); ctx.fillStyle = 'rgba(240,245,246,0.6)'; ctx.fill(); }
  }

  // ---- natural: rock / boulder cluster -------------------------------
  function rocks(ctx, gx, gy, pal, opt) {
    opt = opt || {}; const s = opt.scale || 1; const fl = opt.flags || {};
    blob(ctx, gx, gy, 0.7 * s, H, 0.14);
    const specs = [[0, 0, 0.9, 13], [-0.5, 0.3, 0.6, 9], [0.55, 0.25, 0.5, 8]];
    for (const [dx, dy, sc, hz] of specs) {
      isoBox(ctx, gx + dx * s, gy + dy * s, 0.8 * sc * s, 0.8 * sc * s, hz * s, H, pal.rock,
        { top: shade(pal.rock, 0.12), left: pal.rockDark, right: shade(pal.rock, -0.06) });
    }
    if (fl.snow) { const c = project(gx, gy, H + 13 * s); ctx.beginPath(); ctx.ellipse(c.x, c.y, 18 * s, 9 * s, 0, 0, Math.PI * 2); ctx.fillStyle = 'rgba(240,245,246,0.5)'; ctx.fill(); }
  }

  // ---- lighthouse ----------------------------------------------------
  function lighthouse(ctx, gx, gy, pal, opt, t) {
    opt = opt || {}; const s = opt.scale || 1;
    blob(ctx, gx, gy, 0.8, H, 0.2);
    // tapered tower as stacked cylinders
    isoCylinder(ctx, gx, gy, 0.62, 8, H, '#e9e3d6', { edge: null, top: '#f2ede2' });
    isoCylinder(ctx, gx, gy, 0.5, 34, H + 8, '#dcd5c6', { top: '#ece6da' });
    // red bands
    const band = project(gx, gy, H + 8);
    ctx.save(); ctx.fillStyle = pal.roofWarm;
    for (const yy of [12, 28]) {
      const c = project(gx, gy, H + 8 + yy); const rx = 0.5 * TILE, ry = 0.5 * QUART;
      ctx.beginPath(); ctx.moveTo(c.x - rx, c.y); ctx.lineTo(c.x - rx, c.y + 6); ctx.ellipse(c.x, c.y + 6, rx, ry, 0, Math.PI, 0, true); ctx.lineTo(c.x + rx, c.y); ctx.ellipse(c.x, c.y, rx, ry, 0, 0, Math.PI, false); ctx.closePath(); ctx.fill();
    }
    ctx.restore();
    // lantern room
    isoCylinder(ctx, gx, gy, 0.42, 12, H + 42, '#3a4a52', { top: '#2b383f' });
    const lamp = project(gx, gy, H + 50);
    const glow = 0.5 + 0.5 * Math.sin((t || 0) / 500);
    ctx.beginPath(); ctx.ellipse(lamp.x, lamp.y, 9, 6, 0, 0, Math.PI * 2); ctx.fillStyle = withAlpha('#ffe39a', 0.6 + 0.3 * glow); ctx.fill();
    ctx.beginPath(); ctx.ellipse(lamp.x, lamp.y, 22, 13, 0, 0, Math.PI * 2); ctx.fillStyle = withAlpha('#ffe7a6', 0.10 + 0.12 * glow); ctx.fill();
    // cap
    isoRoof(ctx, gx, gy, 1.0, 1.0, 12, H + 54, pal.roofWarm);
  }

  // ---- windmill (American farm) -------------------------------------
  function windmill(ctx, gx, gy, pal, opt, t) {
    opt = opt || {}; const s = opt.scale || 1;
    blob(ctx, gx, gy, 0.5, H, 0.18);
    const steel = '#3a4750', steelD = '#28323a';
    // lattice tower (trapezoid)
    const baseW = 0.5, topW = 0.18, hgt = 48;
    const bl = project(gx - baseW / 2, gy + baseW / 2, H), br = project(gx + baseW / 2, gy + baseW / 2, H);
    const tl = project(gx - topW / 2, gy + topW / 2, H + hgt), tr = project(gx + topW / 2, gy + topW / 2, H + hgt);
    poly(ctx, [bl, br, tr, tl], steel, steelD, 1);
    // cross braces
    ctx.save(); ctx.strokeStyle = steelD; ctx.lineWidth = 1.4;
    for (let i = 0; i < 4; i++) {
      const f = i / 4, f2 = (i + 1) / 4;
      const a = { x: bl.x + (tl.x - bl.x) * f, y: bl.y + (tl.y - bl.y) * f };
      const b = { x: br.x + (tr.x - br.x) * f2, y: br.y + (tr.y - br.y) * f2 };
      const c = { x: br.x + (tr.x - br.x) * f, y: br.y + (tr.y - br.y) * f };
      const d = { x: bl.x + (tl.x - bl.x) * f2, y: bl.y + (tl.y - bl.y) * f2 };
      ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.moveTo(c.x, c.y); ctx.lineTo(d.x, d.y); ctx.stroke();
    }
    ctx.restore();
    // fan
    const hub = project(gx, gy, H + hgt + 4);
    const rot = (t || 0) / 1400;
    ctx.save(); ctx.translate(hub.x, hub.y);
    for (let i = 0; i < 16; i++) {
      const a = rot + (i / 16) * Math.PI * 2;
      ctx.beginPath(); ctx.moveTo(0, 0);
      ctx.lineTo(Math.cos(a) * 16, Math.sin(a) * 10);
      ctx.strokeStyle = withAlpha('#9aa0a2', 0.9); ctx.lineWidth = 2; ctx.stroke();
    }
    ctx.beginPath(); ctx.arc(0, 0, 3, 0, 6.28); ctx.fillStyle = steelD; ctx.fill();
    // tail vane
    ctx.beginPath(); ctx.moveTo(0, 0); ctx.lineTo(-16, -2); ctx.lineTo(-16, 6); ctx.closePath(); ctx.fillStyle = steel; ctx.fill();
    ctx.restore();
  }

  // ---- farmhouse -----------------------------------------------------
  function farmhouse(ctx, gx, gy, pal, opt, t) {
    opt = opt || {}; const fl = opt.flags || {};
    blob(ctx, gx, gy, 1.3, H, 0.18);
    const wall = pal.building, roofc = pal.roof;
    isoBox(ctx, gx, gy, 1.7, 1.3, 22, H, wall, { edge: shade(wall, -0.35) });
    // glowing windows on front-right face
    const fc = project(gx + 0.85, gy + 0.2, H + 11);
    drawWindowRow(ctx, gx, gy, 1.7, 1.3, 22, pal, fl);
    gableRoof(ctx, gx, gy, 1.95, 1.5, 16, H + 22, roofc);
    if (fl.snow) snowCap(ctx, gx, gy, 1.95, 1.5, H + 22 + 8);
  }

  // window glow helper on the front faces of a box
  function drawWindowRow(ctx, gx, gy, sx, sy, hz, pal, fl) {
    // front-right face midpoints
    const lit = withAlpha(pal.window, fl.snow || fl.bare ? 0.95 : 0.8);
    const frames = shade(pal.building, -0.5);
    // place 2 windows on right face
    for (const u of [-0.22, 0.22]) {
      const p = project(gx + sx / 2, gy + sy * u, H + hz * 0.55);
      ctx.save(); ctx.translate(p.x, p.y);
      ctx.transform(1, 0.5, 0, 1, 0, 0); // skew to right face plane
      ctx.fillStyle = frames; ctx.fillRect(-4.4, -7.2, 8.8, 11.4);
      ctx.fillStyle = lit; ctx.fillRect(-3.2, -6, 6.4, 9);
      ctx.restore();
    }
    // door on left face
    const d = project(gx - sx * 0.1, gy + sy / 2, H + hz * 0.4);
    ctx.save(); ctx.translate(d.x, d.y); ctx.transform(1, -0.5, 0, 1, 0, 0);
    ctx.fillStyle = frames; ctx.fillRect(-4, -10, 8, 14);
    ctx.fillStyle = shade(pal.window, -0.2); ctx.fillRect(-3, -9, 6, 12);
    ctx.restore();
  }

  function snowCap(ctx, gx, gy, sx, sy, topH) {
    const c = project(gx, gy, topH);
    ctx.beginPath(); ctx.ellipse(c.x, c.y, sx * TILE * 0.62, sy * QUART * 1.1, 0, 0, Math.PI * 2);
    ctx.fillStyle = 'rgba(240,245,246,0.7)'; ctx.fill();
  }

  // ---- barn ----------------------------------------------------------
  function barn(ctx, gx, gy, pal, opt) {
    opt = opt || {}; const fl = opt.flags || {};
    blob(ctx, gx, gy, 1.5, H, 0.18);
    const wall = mix(pal.roofWarm, '#7a3a26', 0.25);
    isoBox(ctx, gx, gy, 1.9, 1.5, 20, H, wall, { edge: shade(wall, -0.4) });
    // big door
    const d = project(gx + 0.95, gy, H + 9);
    ctx.save(); ctx.translate(d.x, d.y); ctx.transform(1, 0.5, 0, 1, 0, 0);
    ctx.fillStyle = shade(wall, -0.4); ctx.fillRect(-9, -12, 18, 18);
    ctx.strokeStyle = mix(wall, '#fff', 0.5); ctx.lineWidth = 1.4; ctx.beginPath(); ctx.moveTo(-9, -3); ctx.lineTo(9, -3); ctx.moveTo(0, -12); ctx.lineTo(0, 6); ctx.stroke();
    ctx.restore();
    // gambrel-ish roof (two gables)
    gableRoof(ctx, gx, gy, 2.15, 1.7, 15, H + 20, pal.roof);
    if (fl.snow) snowCap(ctx, gx, gy, 2.15, 1.7, H + 20 + 7);
  }

  // ---- silo / storage building --------------------------------------
  function silo(ctx, gx, gy, pal, opt) {
    opt = opt || {}; const fl = opt.flags || {};
    blob(ctx, gx, gy, 0.7, H, 0.18);
    isoCylinder(ctx, gx, gy, 0.52, 40, H, mix('#cdd3d0', pal.sandDark, 0.25), { top: '#cfd5d2' });
    // dome
    const c = project(gx, gy, H + 40);
    ctx.beginPath(); ctx.ellipse(c.x, c.y - 4, 0.52 * TILE, 0.52 * QUART + 8, 0, Math.PI, 0); ctx.fillStyle = shade(pal.roof, 0.1); ctx.fill();
    if (fl.snow) { ctx.beginPath(); ctx.ellipse(c.x, c.y - 8, 0.5 * TILE, 0.4 * QUART + 5, 0, Math.PI, 0); ctx.fillStyle = 'rgba(240,245,246,0.7)'; ctx.fill(); }
  }

  // ---- industrial kitchen / packing house (low warehouse) -----------
  function packhouse(ctx, gx, gy, pal, opt) {
    opt = opt || {}; const fl = opt.flags || {};
    blob(ctx, gx, gy, 1.4, H, 0.16);
    const wall = mix(pal.building, '#cfcabf', 0.45);
    isoBox(ctx, gx, gy, 2.0, 1.4, 16, H, wall, { edge: shade(wall, -0.3) });
    // flat roof + vents
    const top = project(gx, gy, H + 16);
    isoBox(ctx, gx, gy - 0.2, 0.5, 0.5, 5, H + 16, shade(pal.building, -0.1));
    drawWindowRow(ctx, gx, gy, 2.0, 1.4, 16, pal, fl);
    if (fl.snow) snowCap2(ctx, gx, gy, 2.0, 1.4, H + 16);
  }
  function snowCap2(ctx, gx, gy, sx, sy, topH) {
    const A = project(gx - sx / 2, gy - sy / 2, topH), B = project(gx + sx / 2, gy - sy / 2, topH), C = project(gx + sx / 2, gy + sy / 2, topH), D = project(gx - sx / 2, gy + sy / 2, topH);
    poly(ctx, [A, B, C, D], 'rgba(240,245,246,0.75)');
  }

  // ---- market stall (striped awning) --------------------------------
  function stall(ctx, gx, gy, pal, opt) {
    blob(ctx, gx, gy, 0.8, H, 0.14);
    // posts
    for (const [dx, dy] of [[-0.5, -0.4], [0.5, -0.4], [-0.5, 0.4], [0.5, 0.4]]) isoBox(ctx, gx + dx, gy + dy, 0.05, 0.05, 14, H, pal.trunk);
    // awning striped
    const A = project(gx - 0.65, gy - 0.55, H + 15), B = project(gx + 0.65, gy - 0.55, H + 15), C = project(gx + 0.65, gy + 0.55, H + 13), D = project(gx - 0.65, gy + 0.55, H + 13);
    poly(ctx, [A, B, C, D], '#cfe3e4');
    ctx.save(); poly(ctx, [A, B, C, D]); ctx.clip();
    ctx.strokeStyle = pal.roofWarm; ctx.lineWidth = 5;
    for (let i = -6; i < 8; i++) { ctx.beginPath(); ctx.moveTo(A.x + i * 9, A.y - 4); ctx.lineTo(D.x + i * 9, D.y + 20); ctx.stroke(); }
    ctx.restore();
    // produce crates
    isoBox(ctx, gx, gy + 0.2, 0.5, 0.3, 5, H, pal.woodDock);
    const cr = project(gx, gy + 0.1, H + 5); ctx.fillStyle = pal.roofWarm; for (let i = 0; i < 5; i++) { ctx.beginPath(); ctx.arc(cr.x - 8 + i * 4, cr.y - 2, 2.2, 0, 6.28); ctx.fill(); }
  }

  // ---- dock (wood platform over water) ------------------------------
  function dock(ctx, gx, gy, pal, opt) {
    opt = opt || {}; const w = opt.w || 1.4, l = opt.l || 2.2;
    // platform slightly above water (elevation small)
    const e = 4;
    const A = project(gx - w / 2, gy - l / 2, e), B = project(gx + w / 2, gy - l / 2, e), C = project(gx + w / 2, gy + l / 2, e), D = project(gx - w / 2, gy + l / 2, e);
    // posts
    for (const t of [-0.5, 0, 0.5]) for (const s of [-0.5, 0.5]) { const pb = project(gx + s * w * 0.8, gy + t * l, e); ctx.fillStyle = pal.woodDockDark; ctx.fillRect(pb.x - 1.5, pb.y, 3, 12); }
    poly(ctx, [A, B, C, D], pal.woodDock, pal.woodDockDark, 1);
    // planks
    ctx.save(); poly(ctx, [A, B, C, D]); ctx.clip(); ctx.strokeStyle = withAlpha(pal.woodDockDark, 0.6); ctx.lineWidth = 1;
    for (let i = 1; i < 8; i++) { const pa = project(gx - w / 2 + (w * i / 8), gy - l / 2, e), pb = project(gx - w / 2 + (w * i / 8), gy + l / 2, e); ctx.beginPath(); ctx.moveTo(pa.x, pa.y); ctx.lineTo(pb.x, pb.y); ctx.stroke(); }
    ctx.restore();
  }

  // ---- fishing boat (in water) --------------------------------------
  function fishingBoat(ctx, gx, gy, pal, opt, t) {
    opt = opt || {};
    const bob = Math.sin((t || 0) / 700 + gx) * 1.2;
    const e = 2 + bob;
    // hull
    const hl = 1.4, hw = 0.7;
    const bow = project(gx, gy - hl / 2, e), sternL = project(gx - hw / 2, gy + hl / 2, e), sternR = project(gx + hw / 2, gy + hl / 2, e);
    const bowB = project(gx, gy - hl / 2, e - 7), sLB = project(gx - hw / 2, gy + hl / 2, e - 7), sRB = project(gx + hw / 2, gy + hl / 2, e - 7);
    poly(ctx, [sternL, sternR, sRB, sLB], shade(pal.building, -0.2));
    poly(ctx, [bow, sternR, sRB, bowB], shade(pal.building, -0.1));
    poly(ctx, [bow, sternL, sLB, bowB], shade(pal.building, -0.3));
    poly(ctx, [bow, sternR, sternL], mix(pal.building, '#e8e3d8', 0.6)); // deck
    // cabin
    isoBox(ctx, gx, gy + 0.2, 0.45, 0.5, 9, e + 0.5, mix(pal.building, '#dfe6e6', 0.7));
    const cw = project(gx + 0.22, gy + 0.2, e + 5); ctx.fillStyle = withAlpha(pal.window, 0.8); ctx.fillRect(cw.x - 2, cw.y - 3, 5, 5);
  }

  // ---- fish pen (ring net in water) ---------------------------------
  function fishPen(ctx, gx, gy, pal, opt, t) {
    const e = 3, r = 0.55;
    const c = project(gx, gy, e);
    ctx.save();
    ctx.strokeStyle = pal.woodDock; ctx.lineWidth = 3;
    ctx.beginPath(); ctx.ellipse(c.x, c.y, r * TILE, r * QUART, 0, 0, Math.PI * 2); ctx.stroke();
    ctx.strokeStyle = withAlpha('#1b3640', 0.4); ctx.lineWidth = 1; ctx.beginPath(); ctx.ellipse(c.x, c.y + 3, r * TILE * 0.9, r * QUART * 0.9, 0, 0, Math.PI * 2); ctx.stroke();
    // a couple of fish flicks
    const fr = (t || 0) / 600;
    for (let i = 0; i < 3; i++) { const a = fr + i * 2.1; ctx.beginPath(); ctx.ellipse(c.x + Math.cos(a) * r * TILE * 0.5, c.y + Math.sin(a) * r * QUART * 0.5, 2.4, 1.2, a, 0, 6.28); ctx.fillStyle = withAlpha('#cfe0d8', 0.7); ctx.fill(); }
    ctx.restore();
  }

  // ---- cattle (herd of simple cows) ---------------------------------
  function cattle(ctx, gx, gy, pal, opt) {
    opt = opt || {}; const n = opt.n || 4; const rng = I.makeRNG((opt.seed || 1) * 31 + 7);
    const spots = [];
    for (let i = 0; i < n; i++) spots.push([gx + (rng() - 0.5) * 2.2, gy + (rng() - 0.5) * 1.6, rng()]);
    spots.sort((a, b) => (a[0] + a[1]) - (b[0] + b[1]));
    for (const [x, y, r] of spots) {
      blob(ctx, x, y, 0.34, H, 0.16);
      const brown = r > 0.5 ? '#8a5a36' : '#6b4a30';
      isoBox(ctx, x, y, 0.5, 0.28, 6, H, brown, { top: shade(brown, 0.1) });
      // white patch
      const c = project(x, y, H + 6); ctx.fillStyle = '#e6ddcf'; ctx.beginPath(); ctx.ellipse(c.x + 2, c.y, 3, 1.6, 0, 0, 6.28); ctx.fill();
      // head
      isoBox(ctx, x - 0.18, y - 0.16, 0.18, 0.16, 5, H + 1, shade(brown, -0.05));
    }
  }

  // ---- tractor -------------------------------------------------------
  function tractor(ctx, gx, gy, pal, opt) {
    blob(ctx, gx, gy, 0.6, H, 0.18);
    const body = pal.roofWarm, body2 = mix(pal.roofWarm, '#c8b048', 0.5);
    // rear big wheels
    wheel(ctx, gx - 0.3, gy + 0.28, 6.5);
    wheel(ctx, gx - 0.3, gy - 0.28, 6.5);
    // body
    isoBox(ctx, gx, gy, 0.75, 0.5, 8, H + 2, body2, { top: shade(body2, 0.1) });
    // cabin
    isoBox(ctx, gx - 0.18, gy, 0.4, 0.42, 9, H + 9, body, { top: shade(body, 0.12) });
    const w = project(gx - 0.0, gy + 0.2, H + 14); ctx.fillStyle = withAlpha('#bfe0e4', 0.8); ctx.fillRect(w.x - 2, w.y - 4, 5, 5);
    // front small wheels
    wheel(ctx, gx + 0.34, gy + 0.24, 4);
    wheel(ctx, gx + 0.34, gy - 0.24, 4);
  }
  function wheel(ctx, gx, gy, rad) {
    const c = project(gx, gy, H + rad * 0.5);
    ctx.beginPath(); ctx.ellipse(c.x, c.y, rad, rad * 0.92, 0, 0, 6.28); ctx.fillStyle = '#2a2622'; ctx.fill();
    ctx.beginPath(); ctx.ellipse(c.x, c.y, rad * 0.45, rad * 0.42, 0, 0, 6.28); ctx.fillStyle = '#7a756c'; ctx.fill();
  }

  // ---- combine harvester --------------------------------------------
  function combine(ctx, gx, gy, pal, opt) {
    blob(ctx, gx, gy, 0.9, H, 0.18);
    const body = mix(pal.roofWarm, '#b83a26', 0.2);
    wheel(ctx, gx - 0.4, gy + 0.34, 7); wheel(ctx, gx - 0.4, gy - 0.34, 7);
    isoBox(ctx, gx, gy, 1.0, 0.6, 12, H + 3, body, { top: shade(body, 0.1) });
    isoBox(ctx, gx - 0.2, gy, 0.4, 0.5, 9, H + 15, mix(body, '#fff', 0.2));
    // header reel up front
    isoBox(ctx, gx + 0.7, gy, 0.25, 0.9, 4, H, '#cdd3d0');
    wheel(ctx, gx + 0.5, gy + 0.34, 4); wheel(ctx, gx + 0.5, gy - 0.34, 4);
  }

  // ---- pickup truck --------------------------------------------------
  function pickup(ctx, gx, gy, pal, opt) {
    blob(ctx, gx, gy, 0.5, H, 0.16);
    const body = mix(pal.building, '#8aa0a0', 0.4);
    wheel(ctx, gx - 0.3, gy + 0.22, 4); wheel(ctx, gx - 0.3, gy - 0.22, 4);
    wheel(ctx, gx + 0.3, gy + 0.22, 4); wheel(ctx, gx + 0.3, gy - 0.22, 4);
    isoBox(ctx, gx + 0.1, gy, 0.5, 0.4, 5, H + 2, body); // bed
    isoBox(ctx, gx - 0.22, gy, 0.32, 0.4, 8, H + 2, shade(body, 0.08)); // cab
  }

  // ---- warehouse (storage building) ---------------------------------
  function warehouse(ctx, gx, gy, pal, opt) {
    opt = opt || {}; const fl = opt.flags || {};
    blob(ctx, gx, gy, 2.0, H, 0.16);
    const wall = mix('#d0cfc8', pal.sandDark, 0.18); // light grey
    const roofC = mix('#8a9090', pal.rock, 0.5);     // corrugated steel
    // main body — wide & low
    isoBox(ctx, gx, gy, 2.8, 1.6, 14, H, wall, {
      top: mix(wall, '#fff', 0.12),
      left: shade(wall, -0.22),
      right: shade(wall, -0.10),
      edge: shade(wall, -0.35)
    });
    // flat roof with slight parapet
    const A = I.project(gx - 1.4, gy - 0.8, H + 14);
    const B = I.project(gx + 1.4, gy - 0.8, H + 14);
    const C = I.project(gx + 1.4, gy + 0.8, H + 14);
    const D = I.project(gx - 1.4, gy + 0.8, H + 14);
    poly(ctx, [A, B, C, D], mix(roofC, '#fff', 0.12), shade(roofC, -0.2), 1);
    // corrugated ridge lines on roof
    ctx.save();
    poly(ctx, [A, B, C, D]); ctx.clip();
    ctx.strokeStyle = withAlpha(shade(roofC, -0.25), 0.55); ctx.lineWidth = 1;
    for (let i = -4; i <= 4; i++) {
      const pa = I.project(gx + i * 0.32, gy - 0.8, H + 14.5);
      const pb = I.project(gx + i * 0.32, gy + 0.8, H + 14.5);
      ctx.beginPath(); ctx.moveTo(pa.x, pa.y); ctx.lineTo(pb.x, pb.y); ctx.stroke();
    }
    ctx.restore();
    // roller door on right face (2 bays)
    for (const du of [-0.55, 0.55]) {
      const dp = I.project(gx + 1.4, gy + du, H + 6);
      ctx.save(); ctx.translate(dp.x, dp.y); ctx.transform(1, 0.5, 0, 1, 0, 0);
      ctx.fillStyle = shade(wall, -0.40); ctx.fillRect(-8.5, -10, 17, 14);
      ctx.strokeStyle = withAlpha(wall, 0.9); ctx.lineWidth = 1;
      for (let r = 0; r < 4; r++) { ctx.beginPath(); ctx.moveTo(-8.5, -10 + r * 3.5); ctx.lineTo(8.5, -10 + r * 3.5); ctx.stroke(); }
      ctx.restore();
    }
    // loading bay bumper strip
    const bump = I.project(gx + 1.4, gy, H + 2);
    ctx.save(); ctx.translate(bump.x, bump.y); ctx.transform(1, 0.5, 0, 1, 0, 0);
    ctx.fillStyle = withAlpha(pal.roofWarm, 0.9); ctx.fillRect(-20, -2, 40, 4);
    ctx.restore();
    if (fl.snow) snowCap2(ctx, gx, gy, 2.8, 1.6, H + 14);
  }

  // ---- kitchen / farmhouse kitchen (standalone cottage) --------------
  function kitchenCottage(ctx, gx, gy, pal, opt, t) {
    opt = opt || {}; const fl = opt.flags || {};
    blob(ctx, gx, gy, 1.0, H, 0.16);
    // warm terracotta walls — distinct from dark-teal buildings
    const wall = mix(pal.sandDark, pal.roofWarm, 0.55);
    const roofC = mix(pal.roofWarm, '#7a3a26', 0.35);
    isoBox(ctx, gx, gy, 1.3, 1.1, 18, H, wall, { edge: shade(wall, -0.35) });
    // chimney stack (left-back)
    isoBox(ctx, gx - 0.35, gy - 0.3, 0.22, 0.22, 10, H + 16, shade(wall, -0.18));
    const smoke = I.project(gx - 0.35, gy - 0.3, H + 28);
    ctx.save(); ctx.fillStyle = withAlpha('#ccc', 0.35); ctx.filter = 'blur(3px)';
    ctx.beginPath(); ctx.ellipse(smoke.x, smoke.y - 3, 5, 4, 0, 0, 6.28); ctx.fill();
    ctx.beginPath(); ctx.ellipse(smoke.x - 2, smoke.y - 9, 7, 5, 0, 0, 6.28); ctx.fill();
    ctx.restore();
    // gable roof
    gableRoof(ctx, gx, gy, 1.5, 1.3, 13, H + 18, roofC);
    // window with warm glow
    const w = I.project(gx + 0.65, gy + 0.1, H + 9);
    ctx.save(); ctx.translate(w.x, w.y); ctx.transform(1, 0.5, 0, 1, 0, 0);
    ctx.fillStyle = shade(wall, -0.45); ctx.fillRect(-4, -6, 8, 9);
    ctx.fillStyle = withAlpha(mix(pal.window, '#ffb840', 0.35), 0.95); ctx.fillRect(-3, -5, 6, 7.5);
    ctx.restore();
    // door on left-front face
    const dor = I.project(gx, gy + 0.55, H + 7);
    ctx.save(); ctx.translate(dor.x, dor.y); ctx.transform(1, -0.5, 0, 1, 0, 0);
    ctx.fillStyle = shade(wall, -0.45); ctx.fillRect(-3.5, -9, 7, 12);
    ctx.fillStyle = mix(pal.woodDock, '#8a5030', 0.4); ctx.fillRect(-2.5, -8, 5, 10);
    ctx.restore();
    if (fl.snow) snowCap(ctx, gx, gy, 1.5, 1.3, H + 18 + 6);
  }

  // ---- rocky mountain -----------------------------------------------
  function mountain(ctx, gx, gy, pal, opt, t) {
    opt = opt || {}; const fl = opt.flags || {};
    const s = opt.scale || 1;
    const rock = pal.rock, rockD = pal.rockDark;
    const smoke = fl.drought ? null : (fl.snow ? '#e8ecea' : '#c8cec8');
    // tiers: [{blocks:[{dx,dy},…], baseH, blockH, blockS}]
    const tiers = [
      { pts: [[-1.6,-0.4],[-1.1,-1.3],[-0.3,-1.6],[0.6,-1.4],[1.4,-0.7],[1.6,0.3],[0.8,1.2],[-0.4,1.4],[-1.3,0.8]], bH:0, hgt:18, bs:0.85 },
      { pts: [[-1.1,-0.2],[-0.7,-0.9],[-0.1,-1.2],[0.6,-0.9],[1.1,-0.2],[0.9,0.6],[0.1,1.0],[-0.7,0.6]], bH:14, hgt:20, bs:0.75 },
      { pts: [[-0.6,-0.1],[-0.3,-0.7],[0.3,-0.8],[0.7,-0.2],[0.6,0.4],[0.0,0.7],[-0.5,0.3]], bH:28, hgt:20, bs:0.6 },
      { pts: [[-0.3,0.0],[0.0,-0.4],[0.4,-0.2],[0.3,0.3],[-0.1,0.4]], bH:43, hgt:18, bs:0.48 },
      { pts: [[-0.1,-0.1],[0.1,0.0],[0.0,0.2]], bH:56, hgt:18, bs:0.38 },
    ];
    // sort each tier by depth (painter's algo within tier)
    for (const tier of tiers) {
      const sorted = [...tier.pts].sort((a,b) => (a[0]+a[1]) - (b[0]+b[1]));
      const rng = I.makeRNG(opt.seed || 7);
      for (const [dx,dy] of sorted) {
        const bx = gx + dx*s, by = gy + dy*s;
        const jitter = 0.8 + rng()*0.4;
        const topC = rng() > 0.5 ? shade(rock, 0.06+rng()*0.08) : shade(rockD, 0.05);
        isoBox(ctx, bx, by, tier.bs*s*jitter, tier.bs*s*jitter, tier.hgt*s*jitter, H + tier.bH*s,
          topC, { left: shade(rockD,-0.06), right: shade(rock,-0.12), edge: null });
      }
      // snow cap on tiers 2+
      if (fl.snow && tier.bH >= 28) {
        for (const [dx,dy] of sorted) {
          const bx = gx+dx*s, by = gy+dy*s;
          const p = I.project(bx, by, H + tier.bH*s + tier.hgt*s);
          ctx.beginPath(); ctx.ellipse(p.x, p.y, tier.bs*s*TILE*0.55, tier.bs*s*QUART*0.7, 0, 0, 6.28);
          ctx.fillStyle = 'rgba(238,244,245,0.75)'; ctx.fill();
        }
      }
    }
    // smoke puff from peak vent
    if (smoke && !fl.drought) {
      const peak = I.project(gx + 0.05*s, gy - 0.1*s, H + 75*s);
      ctx.save(); ctx.filter = 'blur(5px)';
      const puffs = [[0,-3,12,8,0.30],[-8,-14,14,9,0.22],[5,-22,11,7,0.18],[0,-32,16,10,0.14]];
      for (const [px,py,rx,ry,a] of puffs) {
        ctx.beginPath(); ctx.ellipse(peak.x+px, peak.y+py, rx, ry, 0, 0, 6.28);
        ctx.fillStyle = withAlpha(smoke, a); ctx.fill();
      }
      ctx.restore();
    }
  }

  // ---- mine entrance (tunnel mouth) ---------------------------------
  function mineEntrance(ctx, gx, gy, pal, opt) {
    opt = opt || {};
    const steel = '#3a4750', wood = pal.woodDock, dark = '#181e22';
    // rock surround
    isoBox(ctx, gx-0.3, gy-0.2, 0.35, 0.5, 18, H, shade(pal.rock,-0.10));
    isoBox(ctx, gx+0.3, gy-0.2, 0.35, 0.5, 18, H, pal.rock);
    isoBox(ctx, gx, gy-0.55, 0.8, 0.35, 12, H+18, shade(pal.rock,0.05));
    // tunnel dark void
    const mouth = I.project(gx, gy, H+7);
    ctx.save(); ctx.translate(mouth.x, mouth.y);
    ctx.fillStyle = dark; ctx.beginPath(); ctx.ellipse(0, 0, 14, 10, 0, Math.PI, 0); ctx.fill();
    // timber supports
    ctx.strokeStyle = wood; ctx.lineWidth = 2.5;
    ctx.beginPath(); ctx.moveTo(-12, 0); ctx.lineTo(-12, -9); ctx.lineTo(12, -9); ctx.lineTo(12, 0); ctx.stroke();
    // rail tracks leading out
    ctx.strokeStyle = steel; ctx.lineWidth = 1.5;
    ctx.beginPath(); ctx.moveTo(-6, 0); ctx.lineTo(-7, 16); ctx.moveTo(6, 0); ctx.lineTo(7, 16);
    ctx.moveTo(-7,8); ctx.lineTo(7,8); ctx.stroke();
    ctx.restore();
  }

  // ---- oil derrick (pump jack) --------------------------------------
  function oilDerrick(ctx, gx, gy, pal, opt, t) {
    opt = opt || {}; const s = opt.scale || 1; const fl = opt.flags || {};
    blob(ctx, gx, gy, 0.7*s, H, 0.15);
    const steel = '#2e3d48', steelL = '#4a5d6a';
    const hgt = 52*s;
    // concrete base pad
    isoBox(ctx, gx, gy, 0.7*s, 0.7*s, 4, H, mix(pal.sand,'#aaa',0.3));
    // lattice tower legs (4 lines converging to top)
    const base = [ I.project(gx-0.28*s,gy-0.28*s,H+4), I.project(gx+0.28*s,gy-0.28*s,H+4),
                   I.project(gx+0.28*s,gy+0.28*s,H+4), I.project(gx-0.28*s,gy+0.28*s,H+4) ];
    const peak = I.project(gx,gy,H+4+hgt);
    ctx.save(); ctx.strokeStyle=steel; ctx.lineWidth=2.5*s;
    for (const b of base) { ctx.beginPath(); ctx.moveTo(b.x,b.y); ctx.lineTo(peak.x,peak.y); ctx.stroke(); }
    // cross braces
    ctx.lineWidth=1.2*s; ctx.strokeStyle=steelL;
    for (let i=0;i<5;i++) {
      const f=i/5, f2=(i+1)/5;
      for (let j=0;j<4;j++) {
        const a=base[j], b=base[(j+1)%4];
        const p0={x:a.x+(peak.x-a.x)*f, y:a.y+(peak.y-a.y)*f};
        const p1={x:b.x+(peak.x-b.x)*f2,y:b.y+(peak.y-b.y)*f2};
        const p2={x:b.x+(peak.x-b.x)*f, y:b.y+(peak.y-b.y)*f};
        const p3={x:a.x+(peak.x-a.x)*f2,y:a.y+(peak.y-a.y)*f2};
        ctx.beginPath(); ctx.moveTo(p0.x,p0.y); ctx.lineTo(p1.x,p1.y); ctx.stroke();
        ctx.beginPath(); ctx.moveTo(p2.x,p2.y); ctx.lineTo(p3.x,p3.y); ctx.stroke();
      }
    }
    // pump jack walking beam
    const pivot = I.project(gx,gy,H+4+hgt*0.72);
    const rot = Math.sin((t||0)/600) * 0.4;
    const beamL = 22*s, counterL = 14*s;
    ctx.save(); ctx.translate(pivot.x,pivot.y); ctx.rotate(rot);
    ctx.strokeStyle=steel; ctx.lineWidth=3*s;
    ctx.beginPath(); ctx.moveTo(-counterL,-4); ctx.lineTo(beamL,4); ctx.stroke();
    // horse head
    ctx.fillStyle=steel; ctx.beginPath(); ctx.rect(beamL-4,-2,8,10); ctx.fill();
    // counterweight
    ctx.fillStyle=steelL; ctx.beginPath(); ctx.ellipse(-counterL,-4,8*s,6*s,0,0,6.28); ctx.fill();
    ctx.restore();
    // sucker rod down to ground
    const rodTop = I.project(gx+0.15*s, gy, H+4+hgt*0.72 + Math.sin((t||0)/600)*12*s);
    const rodBot = I.project(gx+0.15*s, gy, H+4);
    ctx.beginPath(); ctx.moveTo(rodTop.x,rodTop.y); ctx.lineTo(rodBot.x,rodBot.y);
    ctx.strokeStyle=steelL; ctx.lineWidth=1.5*s; ctx.stroke();
    ctx.restore();
    // smoke/steam not usual for pump jack — oil vapor
    if (!fl.drought && !fl.snow) {
      const vent = I.project(gx,gy,H+4+hgt+4);
      ctx.save(); ctx.fillStyle=withAlpha('#8a9898',0.25); ctx.filter='blur(3px)';
      ctx.beginPath(); ctx.ellipse(vent.x,vent.y-3,5,4,0,0,6.28); ctx.fill();
      ctx.restore();
    }
  }

  // ---- crusher (jaw crusher / industrial) ---------------------------
  function crusher(ctx, gx, gy, pal, opt, t) {
    opt = opt || {}; const fl = opt.flags || {};
    blob(ctx, gx, gy, 1.0, H, 0.15);
    const body = mix(pal.building,'#556068',0.5);
    const accent = mix(pal.roofWarm,'#c87828',0.35);
    // base frame (heavy steel)
    isoBox(ctx, gx, gy, 1.1, 0.9, 12, H, body, { edge: shade(body,-0.3), left: shade(body,-0.28), right: shade(body,-0.14) });
    // hopper funnel on top
    const hopperPts = [
      I.project(gx-0.35,gy-0.28,H+12), I.project(gx+0.35,gy-0.28,H+12),
      I.project(gx+0.35,gy+0.28,H+12), I.project(gx-0.35,gy+0.28,H+12),
    ];
    const hopperTop = [
      I.project(gx-0.55,gy-0.45,H+24), I.project(gx+0.55,gy-0.45,H+24),
      I.project(gx+0.55,gy+0.45,H+24), I.project(gx-0.55,gy+0.45,H+24),
    ];
    // hopper side walls
    poly(ctx,[hopperPts[3],hopperPts[2],hopperTop[2],hopperTop[3]], shade(body,-0.22));
    poly(ctx,[hopperPts[2],hopperPts[1],hopperTop[1],hopperTop[2]], shade(body,-0.10));
    poly(ctx,[hopperTop[0],hopperTop[1],hopperTop[2],hopperTop[3]], shade(body,0.06));
    // ore input chute (dark opening)
    ctx.save(); ctx.translate((hopperTop[0].x+hopperTop[2].x)/2,(hopperTop[0].y+hopperTop[2].y)/2);
    ctx.fillStyle='rgba(8,12,16,0.8)'; ctx.beginPath(); ctx.ellipse(0,0,12,7,0,0,6.28); ctx.fill();
    ctx.restore();
    // flywheel on side
    const fw = I.project(gx+0.55,gy-0.1,H+8);
    ctx.save(); ctx.translate(fw.x,fw.y);
    const fwRot = (t||0)/300;
    ctx.strokeStyle=accent; ctx.lineWidth=2;
    ctx.beginPath(); ctx.ellipse(0,0,10,7,0,0,6.28); ctx.stroke();
    for (let i=0;i<4;i++) { const a=fwRot+i*Math.PI/2;
      ctx.beginPath(); ctx.moveTo(0,0); ctx.lineTo(Math.cos(a)*9,Math.sin(a)*6); ctx.stroke(); }
    ctx.restore();
    // output chute angled down-right
    const ch1 = I.project(gx+0.55,gy+0.35,H+4), ch2 = I.project(gx+1.1,gy+0.7,H);
    ctx.strokeStyle=body; ctx.lineWidth=6; ctx.beginPath(); ctx.moveTo(ch1.x,ch1.y); ctx.lineTo(ch2.x,ch2.y); ctx.stroke();
    // ore pile under chute
    oreHeap(ctx, gx+1.0, gy+0.8, pal, { scale: 0.7, flags:fl });
  }

  // ---- ore heap (gravel mound) --------------------------------------
  function oreHeap(ctx, gx, gy, pal, opt) {
    opt = opt || {}; const s = opt.scale || 1; const fl = opt.flags || {};
    const oreC = fl.drought ? mix('#8a6a3a','#a87840',0.5) : mix(pal.rockDark,'#7a5830',0.55);
    const c = I.project(gx, gy, H);
    ctx.save();
    const rx = 18*s, ry = 10*s;
    // shadow
    ctx.beginPath(); ctx.ellipse(c.x+2,c.y+3,rx*0.95,ry*0.75,0,0,6.28); ctx.fillStyle='rgba(12,18,24,0.2)'; ctx.fill();
    // base mound
    ctx.beginPath(); ctx.ellipse(c.x,c.y,rx,ry,0,0,6.28); ctx.fillStyle=oreC; ctx.fill();
    // highlight
    ctx.beginPath(); ctx.ellipse(c.x-4,c.y-4,rx*0.55,ry*0.45,0,0,6.28); ctx.fillStyle=shade(oreC,0.18); ctx.fill();
    // rock chunks
    const rng=I.makeRNG((opt.seed||3)*17);
    for (let i=0;i<8;i++) {
      const a=rng()*6.28, r=rng()*rx*0.7;
      ctx.fillStyle=rng()>0.5?oreC:shade(oreC,-0.15);
      ctx.beginPath(); ctx.ellipse(c.x+Math.cos(a)*r*0.9,c.y+Math.sin(a)*r*0.5-4,3+rng()*3,2+rng()*2,rng()*3,0,6.28); ctx.fill();
    }
    if (fl.snow) { ctx.beginPath(); ctx.ellipse(c.x,c.y-3,rx*0.5,ry*0.4,0,0,6.28); ctx.fillStyle='rgba(238,243,244,0.7)'; ctx.fill(); }
    ctx.restore();
  }

  // ---- smelter / enhanced crusher-smelter --------------------------
  function smelter(ctx, gx, gy, pal, opt, t) {
    opt = opt || {}; const fl = opt.flags || {};
    blob(ctx, gx, gy, 1.8, H, 0.16);
    const brick = mix(pal.roofWarm,'#5a3820',0.45);
    const metal = mix(pal.building,'#4a5a62',0.5);
    // main hall
    isoBox(ctx, gx, gy, 2.4, 1.5, 20, H, brick, { top: shade(brick,0.06), left: shade(brick,-0.30), right: shade(brick,-0.15), edge: null });
    // attached front shed
    isoBox(ctx, gx+1.2, gy+0.3, 0.8, 0.85, 14, H, shade(metal,-0.05));
    // two big chimneys
    for (const [dx,dy] of [[-0.55,-0.30],[0.25,-0.25]]) {
      isoCylinder(ctx, gx+dx, gy+dy, 0.22, 36, H+20, metal, { top: shade(metal,-0.2) });
      // red warning band
      const band = I.project(gx+dx, gy+dy, H+50);
      ctx.save(); ctx.translate(band.x,band.y); ctx.fillStyle=pal.roofWarm;
      const rx2=0.22*TILE, ry2=0.22*QUART;
      ctx.beginPath(); ctx.moveTo(-rx2,0); ctx.lineTo(-rx2,4); ctx.ellipse(0,4,rx2,ry2,0,Math.PI,0,true); ctx.lineTo(rx2,0); ctx.ellipse(0,0,rx2,ry2,0,0,Math.PI,false); ctx.closePath(); ctx.fill();
      ctx.restore();
      // smoke
      if (!fl.drought && !fl.bare) {
        const sm = I.project(gx+dx, gy+dy, H+58);
        ctx.save(); ctx.filter='blur(4px)';
        const a0=0.32+0.08*Math.sin((t||0)/400+(dx*7));
        ctx.fillStyle=withAlpha('#9aaa9e',a0); ctx.beginPath(); ctx.ellipse(sm.x,sm.y-4,8,6,0,0,6.28); ctx.fill();
        ctx.fillStyle=withAlpha('#8a9a8e',a0*0.7); ctx.beginPath(); ctx.ellipse(sm.x-4,sm.y-14,12,9,0,0,6.28); ctx.fill();
        ctx.fillStyle=withAlpha('#7a8a7e',a0*0.5); ctx.beginPath(); ctx.ellipse(sm.x+2,sm.y-24,14,10,0,0,6.28); ctx.fill();
        ctx.restore();
      }
    }
    // roller door + windows on front face
    const door = I.project(gx+1.2, gy+0.8, H+8);
    ctx.save(); ctx.translate(door.x,door.y); ctx.transform(1,0.5,0,1,0,0);
    ctx.fillStyle=shade(metal,-0.35); ctx.fillRect(-11,-12,22,17);
    ctx.strokeStyle=withAlpha(metal,0.8); ctx.lineWidth=1.4;
    for (let r=0;r<4;r++) { ctx.beginPath(); ctx.moveTo(-11,-12+r*4); ctx.lineTo(11,-12+r*4); ctx.stroke(); }
    ctx.restore();
    // glowing furnace windows
    for (const u of [-0.35,0.35]) {
      const w = I.project(gx+1.2, gy+u, H+10);
      ctx.save(); ctx.translate(w.x,w.y); ctx.transform(1,0.5,0,1,0,0);
      ctx.fillStyle='rgba(255,120,20,0.85)'; ctx.fillRect(-5,-5,10,8);
      ctx.restore();
    }
  }

  // ---- refinery (tank farm + distillation tower) -------------------
  function refinery(ctx, gx, gy, pal, opt, t) {
    opt = opt || {}; const fl = opt.flags || {};
    blob(ctx, gx, gy, 1.6, H, 0.16);
    const steel = mix(pal.building,'#6a7a80',0.4);
    const tankC = mix('#b0b8b4',pal.sand,0.35);
    // 3 storage tanks
    const tanks = [[-0.6,0.3,0.45,22],[0.3,0.0,0.5,28],[-0.1,0.7,0.40,18]];
    for (const [dx,dy,r,h] of tanks) {
      isoCylinder(ctx, gx+dx, gy+dy, r, h, H, tankC, { top: shade(tankC,0.12), edge: null });
      // measurement bands
      ctx.save();
      const cap = I.project(gx+dx, gy+dy, H+h*0.5);
      ctx.strokeStyle=withAlpha(shade(tankC,-0.3),0.6); ctx.lineWidth=1;
      ctx.beginPath(); ctx.ellipse(cap.x,cap.y,r*TILE,r*QUART,0,0,6.28); ctx.stroke();
      ctx.restore();
    }
    // distillation tower (tall cylinder)
    isoCylinder(ctx, gx+0.6, gy-0.5, 0.28, 52, H, shade(steel,0.05), { top: shade(steel,-0.1) });
    // flare stack beside tower
    const flare = I.project(gx+0.9, gy-0.4, H+52+6);
    ctx.save(); ctx.filter='blur(2px)';
    ctx.fillStyle=withAlpha('#ff8820',0.6+0.2*Math.sin((t||0)/200)); ctx.beginPath(); ctx.ellipse(flare.x,flare.y-3,5,7,0,0,6.28); ctx.fill();
    ctx.fillStyle=withAlpha('#ffcc44',0.4+0.15*Math.sin((t||0)/180+1)); ctx.beginPath(); ctx.ellipse(flare.x,flare.y-6,3,5,0,0,6.28); ctx.fill();
    ctx.restore();
    // pipes connecting tanks (simple lines)
    ctx.save(); ctx.strokeStyle=withAlpha(shade(steel,-0.1),0.85); ctx.lineWidth=3;
    const pipe = (ax,ay,bx,by) => { const pa=I.project(ax,ay,H+4),pb=I.project(bx,by,H+4); ctx.beginPath(); ctx.moveTo(pa.x,pa.y); ctx.lineTo(pb.x,pb.y); ctx.stroke(); };
    pipe(gx-0.6,gy+0.3, gx+0.3,gy+0.0); pipe(gx+0.3,gy+0.0, gx-0.1,gy+0.7); pipe(gx+0.3,gy+0.0, gx+0.6,gy-0.5);
    ctx.restore();
  }

  // ---- dump truck --------------------------------------------------
  function dumpTruck(ctx, gx, gy, pal, opt) {
    opt = opt || {};
    blob(ctx, gx, gy, 0.8, H, 0.18);
    const yellow = mix(pal.roofWarm,'#d4a020',0.6);
    const dark = shade(yellow,-0.35);
    // big rear wheels
    wheel(ctx, gx-0.36, gy+0.38, 8); wheel(ctx, gx-0.36, gy-0.38, 8);
    // body / dumper bed
    isoBox(ctx, gx+0.1, gy, 1.1, 0.7, 10, H+2, yellow, { top: shade(yellow,0.10), left: shade(yellow,-0.25), right: shade(yellow,-0.12), edge: dark });
    // raised dump bed (tilted back)
    const b0=I.project(gx-0.45,gy-0.35,H+11), b1=I.project(gx+0.55,gy-0.35,H+11);
    const b2=I.project(gx+0.55,gy+0.35,H+11), b3=I.project(gx-0.45,gy+0.35,H+11);
    const t0=I.project(gx-0.55,gy-0.38,H+22), t1=I.project(gx-0.45,gy+0.38,H+22);
    poly(ctx,[b3,b2,{x:b2.x,y:b2.y-2},{x:b3.x,y:b3.y-2}], shade(yellow,-0.20));
    poly(ctx,[b0,b1,{x:b1.x,y:b1.y-2},{x:b0.x,y:b0.y-2}], shade(yellow,-0.10));
    poly(ctx,[b0,b1,b2,b3], yellow); // floor
    poly(ctx,[b0,t0,t1,b3], shade(yellow,-0.08)); // back tailgate
    // cab
    isoBox(ctx, gx-0.44, gy, 0.55, 0.65, 14, H+2, shade(yellow,-0.05));
    const cw = I.project(gx-0.44, gy+0.3, H+11);
    ctx.save(); ctx.translate(cw.x,cw.y); ctx.transform(1,-0.5,0,1,0,0);
    ctx.fillStyle=withAlpha('#bfe0e4',0.85); ctx.fillRect(-4,-8,9,9); ctx.restore();
    // small front wheels
    wheel(ctx, gx+0.46, gy+0.30, 5); wheel(ctx, gx+0.46, gy-0.30, 5);
  }

  // ---- supply / cargo boat (mining harbour) -------------------------
  function supplyBoat(ctx, gx, gy, pal, opt, t) {
    opt = opt || {};
    const bob = Math.sin((t||0)/900 + gx*1.3) * 1.4;
    const e = 2 + bob;
    const hl = 2.0, hw = 0.9;
    const brown = mix(pal.building,'#8a5034',0.45);
    // hull sides
    const bow  = I.project(gx, gy-hl/2, e);
    const sL   = I.project(gx-hw/2, gy+hl/2, e);
    const sR   = I.project(gx+hw/2, gy+hl/2, e);
    const bowB = I.project(gx, gy-hl/2, e-9);
    const sLB  = I.project(gx-hw/2, gy+hl/2, e-9);
    const sRB  = I.project(gx+hw/2, gy+hl/2, e-9);
    poly(ctx,[sL,sR,sRB,sLB], shade(brown,-0.20));
    poly(ctx,[bow,sR,sRB,bowB], shade(brown,-0.08));
    poly(ctx,[bow,sL,sLB,bowB], shade(brown,-0.32));
    poly(ctx,[bow,sR,sL], mix(brown,'#d4cfc0',0.5)); // deck
    // cargo crates on deck
    for (const [dx,dy] of [[0.0,0.2],[0.0,0.6]]) {
      isoBox(ctx, gx+dx, gy+dy, 0.35, 0.35, 8, e+0.5, mix(pal.sandDark,pal.roofWarm,0.4));
    }
    // wheelhouse
    isoBox(ctx, gx, gy-0.2, 0.5, 0.6, 10, e+0.5, mix(pal.building,'#dce6e6',0.55));
    const w2 = I.project(gx+0.25, gy-0.25, e+6);
    ctx.save(); ctx.translate(w2.x,w2.y); ctx.transform(1,0.5,0,1,0,0);
    ctx.fillStyle=withAlpha('#bfe0e4',0.85); ctx.fillRect(-2,-4,5,5); ctx.restore();
    // mast
    const mast = I.project(gx, gy-0.55, e+12);
    ctx.strokeStyle='#3a4a52'; ctx.lineWidth=1.5;
    ctx.beginPath(); ctx.moveTo(I.project(gx,gy-0.55,e+0.5).x, I.project(gx,gy-0.55,e+0.5).y); ctx.lineTo(mast.x,mast.y); ctx.stroke();
  }

  // ---- port / jib crane -----------------------------------------------
  function portCrane(ctx, gx, gy, pal, opt, t) {
    opt = opt || {};
    const s       = opt.scale || 1;
    const boomDir = opt.mirror ? -1 : 1;
    const steel   = '#2e3d48';
    const steelL  = '#4a5d6a';
    const yellow  = mix(pal.roofWarm, '#b88010', 0.72);
    const yDark   = shade(yellow, -0.30);

    blob(ctx, gx, gy, 0.9 * s, H, 0.15);

    // Concrete base pad
    isoBox(ctx, gx, gy, 1.0 * s, 1.0 * s, 5, H,
      mix(pal.sand, '#aaa', 0.45),
      { top: mix(pal.sand, '#bbb', 0.4), left: shade(pal.sand, -0.22), right: shade(pal.sand, -0.10) });

    // A-frame legs (spread in gy direction for iso perspective)
    const leg = 0.44 * s;
    for (const dg of [-leg, leg]) {
      isoBox(ctx, gx, gy + dg, 0.13 * s, 0.13 * s, 54 * s, H + 5, steel, {
        top: shade(steel, 0.12), left: shade(steel, -0.20), right: shade(steel, -0.08)
      });
    }

    // Lattice cross-braces
    ctx.save(); ctx.strokeStyle = withAlpha(steelL, 0.72); ctx.lineWidth = 1.2;
    for (let i = 0; i < 5; i++) {
      const f  = i / 5, f2 = (i + 1) / 5;
      const h1 = H + 5 + f  * 54 * s;
      const h2 = H + 5 + f2 * 54 * s;
      const pA = project(gx, gy - leg, h1), pB = project(gx, gy + leg, h2);
      const pC = project(gx, gy - leg, h2), pD = project(gx, gy + leg, h1);
      ctx.beginPath(); ctx.moveTo(pA.x, pA.y); ctx.lineTo(pB.x, pB.y); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(pC.x, pC.y); ctx.lineTo(pD.x, pD.y); ctx.stroke();
    }
    ctx.restore();

    // Saddle plate connecting legs
    isoBox(ctx, gx, gy, 0.20 * s, leg * 2 + 0.13, 8 * s, H + 5 + 54 * s, steel);

    // Machine house
    const machH = H + 5 + 54 * s + 8 * s;
    isoBox(ctx, gx, gy, 0.58 * s, 0.46 * s, 11 * s, machH, yellow, {
      top: shade(yellow, 0.10), left: shade(yellow, -0.25), right: shade(yellow, -0.12), edge: yDark
    });
    const topH = machH + 11 * s;

    // Main boom (toward water = boomDir in gy)
    const boomLen = 2.2 * s;
    isoBox(ctx, gx, gy + boomDir * boomLen * 0.5, 0.12 * s, boomLen, 6 * s, topH, steel, {
      top: shade(steel, 0.1), left: shade(steel, -0.2), right: shade(steel, -0.08)
    });

    // Counter-jib
    const cjLen = 0.72 * s;
    isoBox(ctx, gx, gy - boomDir * cjLen * 0.5, 0.09 * s, cjLen, 5 * s, topH + 2, steelL);

    // Stay cable: machine top → boom tip
    const mTop = project(gx, gy, topH + 3);
    const bTip = project(gx, gy + boomDir * boomLen, topH + 3);
    ctx.save(); ctx.strokeStyle = withAlpha(steelL, 0.58); ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(mTop.x, mTop.y); ctx.lineTo(bTip.x, bTip.y); ctx.stroke();
    ctx.restore();

    // Trolley (animated along boom)
    const tr     = (t || 0) / 3800;
    const trFrac = 0.20 + 0.55 * (0.5 + 0.5 * Math.sin(tr));
    const trGy   = gy + boomDir * trFrac * boomLen;
    isoBox(ctx, gx, trGy, 0.17 * s, 0.17 * s, 5 * s, topH + 6, yellow);

    // Cable + hook (animated length)
    const cTopH   = topH + 6;
    const dropLen = 24 + 10 * Math.abs(Math.sin(tr * 0.6));
    const cTop    = project(gx, trGy, cTopH);
    const cBot    = project(gx, trGy, cTopH - dropLen);
    ctx.save(); ctx.strokeStyle = shade(steel, 0.22); ctx.lineWidth = 1.2;
    ctx.beginPath(); ctx.moveTo(cTop.x, cTop.y); ctx.lineTo(cBot.x, cBot.y); ctx.stroke();
    ctx.restore();
    const hkC = project(gx, trGy, cTopH - dropLen - 3);
    ctx.fillStyle = steel;
    ctx.beginPath(); ctx.arc(hkC.x, hkC.y, 2.8, 0, 6.28); ctx.fill();
  }

  // ---- forklift --------------------------------------------------------
  function forklift(ctx, gx, gy, pal, opt) {
    opt = opt || {};
    blob(ctx, gx, gy, 0.45, H, 0.14);
    const yellow = mix(pal.roofWarm, '#d4a018', 0.72);
    const dark   = shade(yellow, -0.34);

    // Drive wheels (rear)
    wheel(ctx, gx - 0.22, gy + 0.20, 4.2);
    wheel(ctx, gx - 0.22, gy - 0.20, 4.2);
    // Steer wheels (front)
    wheel(ctx, gx + 0.24, gy + 0.16, 3.2);
    wheel(ctx, gx + 0.24, gy - 0.16, 3.2);

    // Body
    isoBox(ctx, gx, gy, 0.54, 0.42, 8, H + 2, yellow, {
      top: shade(yellow, 0.08), left: shade(yellow, -0.24), right: shade(yellow, -0.11)
    });
    // Cab enclosure
    isoBox(ctx, gx - 0.10, gy, 0.30, 0.38, 8, H + 9, shade(yellow, -0.04));

    // Overhead guard frame
    const guH  = H + 18;
    const posts = [[-0.26, -0.20], [-0.26, 0.20], [0.05, -0.20], [0.05, 0.20]];
    ctx.strokeStyle = dark; ctx.lineWidth = 1.5;
    for (const [dx, dy] of posts) {
      const b0 = project(gx + dx, gy + dy, H + 9);
      const b1 = project(gx + dx, gy + dy, guH);
      ctx.beginPath(); ctx.moveTo(b0.x, b0.y); ctx.lineTo(b1.x, b1.y); ctx.stroke();
    }
    const corners = posts.map(([dx, dy]) => project(gx + dx, gy + dy, guH));
    // top rails
    const pairs = [[0,1],[2,3],[0,2],[1,3]];
    for (const [a, b] of pairs) {
      ctx.beginPath(); ctx.moveTo(corners[a].x, corners[a].y); ctx.lineTo(corners[b].x, corners[b].y); ctx.stroke();
    }

    // Mast at front
    isoBox(ctx, gx + 0.33, gy, 0.08, 0.34, 18, H + 2, dark);

    // Forks (extending in +gx direction)
    for (const dgy of [-0.11, 0.11]) {
      const f0 = project(gx + 0.37, gy + dgy, H + 4.5);
      const f1 = project(gx + 0.83, gy + dgy, H + 4.5);
      ctx.strokeStyle = dark; ctx.lineWidth = 2.8;
      ctx.beginPath(); ctx.moveTo(f0.x, f0.y); ctx.lineTo(f1.x, f1.y); ctx.stroke();
    }
  }

  // ---- shipping container stack ----------------------------------------
  function containerStack(ctx, gx, gy, pal, opt) {
    opt = opt || {};
    const rng  = Iso.makeRNG((opt.seed || 1) * 41 + 7);
    const tall = opt.tall;
    const COLS = ['#b83820', '#1a4a8a', '#2a7040', '#c47820', '#5a3a7a', '#1a6878'];
    const pick = () => COLS[Math.floor(rng() * COLS.length)];

    const drawC = (cx, cy, baseH, col) => {
      isoBox(ctx, cx, cy, 0.58, 0.24, 9, baseH, col, {
        top: shade(col, 0.16), left: shade(col, -0.32), right: shade(col, -0.15)
      });
      // door seam on right face
      const dp = project(cx + 0.29, cy, baseH + 4.5);
      ctx.save(); ctx.translate(dp.x, dp.y); ctx.transform(1, 0.5, 0, 1, 0, 0);
      ctx.strokeStyle = withAlpha(shade(col, -0.38), 0.65); ctx.lineWidth = 0.9;
      ctx.strokeRect(-6, -6, 12, 11);
      ctx.beginPath(); ctx.moveTo(0, -6); ctx.lineTo(0, 5); ctx.stroke();
      ctx.restore();
    };

    blob(ctx, gx, gy, 0.92, H, 0.12);
    drawC(gx - 0.33, gy, H,      pick());
    drawC(gx + 0.33, gy, H,      pick());
    drawC(gx,        gy, H + 9,  pick());
    if (tall) drawC(gx, gy, H + 18, pick());
  }

  // ---- cargo ship (large container vessel) ----------------------------
  function cargoShip(ctx, gx, gy, pal, opt, t) {
    opt = opt || {};
    const bob  = Math.sin((t || 0) / 1100 + gx * 0.5) * 1.8;
    const e    = 3 + bob;
    const hl   = 3.2, hw = 1.2;
    const hull = mix(pal.building, '#1e2e38', 0.65);

    const bow  = project(gx,        gy - hl / 2, e);
    const sL   = project(gx - hw/2, gy + hl / 2, e);
    const sR   = project(gx + hw/2, gy + hl / 2, e);
    const bowB = project(gx,        gy - hl / 2, e - 14);
    const sLB  = project(gx - hw/2, gy + hl / 2, e - 14);
    const sRB  = project(gx + hw/2, gy + hl / 2, e - 14);

    poly(ctx, [sL, sR, sRB, sLB],   shade(hull, -0.28));
    poly(ctx, [bow, sR, sRB, bowB],  shade(hull, -0.14));
    poly(ctx, [bow, sL, sLB, bowB],  shade(hull, -0.38));

    // Waterline stripe
    const wle = e - 10;
    const wlL = project(gx - hw/2, gy + hl / 2, wle);
    const wlR = project(gx + hw/2, gy + hl / 2, wle);
    poly(ctx, [wlL, wlR, sRB, sLB], withAlpha(mix(pal.roofWarm, '#a03020', 0.5), 0.80));

    poly(ctx, [bow, sR, sL], mix(hull, '#8a9090', 0.45)); // deck

    // Container stacks (3 columns × 2 tiers)
    const COLS = ['#b83820', '#1a4a8a', '#2a7040'];
    for (let i = 0; i < 3; i++) {
      const cy = gy - 0.7 + i * 0.9;
      const col = COLS[i];
      isoBox(ctx, gx, cy, 0.68, 0.68, 9, e + 0.5, col, {
        top: shade(col, 0.14), left: shade(col, -0.30), right: shade(col, -0.14)
      });
      isoBox(ctx, gx, cy, 0.58, 0.55, 8, e + 9.5, COLS[(i + 1) % 3], {
        top: shade(COLS[(i+1)%3], 0.12), left: shade(COLS[(i+1)%3], -0.28), right: shade(COLS[(i+1)%3], -0.12)
      });
    }

    // Wheelhouse at stern
    isoBox(ctx, gx, gy + hl / 2 - 0.45, 0.62, 0.52, 16, e + 0.5,
      mix(pal.building, '#ccd8d8', 0.52));
    for (const u of [-0.18, 0.18]) {
      const bw = project(gx + 0.31, gy + hl / 2 - 0.45 + u, e + 8);
      ctx.save(); ctx.translate(bw.x, bw.y); ctx.transform(1, 0.5, 0, 1, 0, 0);
      ctx.fillStyle = withAlpha('#bfe0e4', 0.85); ctx.fillRect(-3, -5, 7, 6); ctx.restore();
    }
    // Funnel
    isoCylinder(ctx, gx + 0.12, gy + hl / 2 - 0.65, 0.18, 14, e + 16,
      mix(hull, '#1a2430', 0.6));
  }

  // ---- tugboat ---------------------------------------------------------
  function tugboat(ctx, gx, gy, pal, opt, t) {
    opt = opt || {};
    const bob  = Math.sin((t || 0) / 750 + gy * 1.1) * 1.1;
    const e    = 2 + bob;
    const hl   = 1.5, hw = 0.72;
    const hull = mix(pal.building, '#1a2a3a', 0.55);

    const bow  = project(gx,        gy - hl / 2, e);
    const sL   = project(gx - hw/2, gy + hl / 2, e);
    const sR   = project(gx + hw/2, gy + hl / 2, e);
    const bowB = project(gx,        gy - hl / 2, e - 9);
    const sLB  = project(gx - hw/2, gy + hl / 2, e - 9);
    const sRB  = project(gx + hw/2, gy + hl / 2, e - 9);

    poly(ctx, [sL, sR, sRB, sLB],   shade(hull, -0.24));
    poly(ctx, [bow, sR, sRB, bowB],  shade(hull, -0.12));
    poly(ctx, [bow, sL, sLB, bowB],  shade(hull, -0.34));

    // Red waterline band
    const rle = e - 6;
    const rlL = project(gx - hw/2, gy + hl / 2, rle);
    const rlR = project(gx + hw/2, gy + hl / 2, rle);
    poly(ctx, [rlL, rlR, sRB, sLB], withAlpha('#c03020', 0.82));
    poly(ctx, [bow, sR, sL], mix(hull, '#8a9898', 0.42)); // deck

    // Boxy cabin
    isoBox(ctx, gx, gy, 0.52, 0.62, 13, e + 0.5,
      mix(pal.building, '#ccd8d8', 0.58));
    for (const u of [-0.20, 0.20]) {
      const w = project(gx + 0.26, gy + u, e + 7);
      ctx.save(); ctx.translate(w.x, w.y); ctx.transform(1, 0.5, 0, 1, 0, 0);
      ctx.fillStyle = withAlpha('#bfe0e4', 0.88); ctx.fillRect(-3.5, -4.5, 7, 5.5); ctx.restore();
    }
    // Funnel
    isoCylinder(ctx, gx, gy - 0.12, 0.19, 11, e + 13,
      mix('#1a2a3a', '#3a4a52', 0.55), { top: '#121e28' });
    // Yellow band on funnel
    const fnPt = project(gx, gy - 0.12, e + 20);
    const rx2  = 0.19 * TILE, ry2 = 0.19 * QUART;
    ctx.save(); ctx.fillStyle = '#f0c020';
    ctx.beginPath();
    ctx.moveTo(fnPt.x - rx2, fnPt.y); ctx.lineTo(fnPt.x - rx2, fnPt.y + 3.5);
    ctx.ellipse(fnPt.x, fnPt.y + 3.5, rx2, ry2, 0, Math.PI, 0, true);
    ctx.lineTo(fnPt.x + rx2, fnPt.y);
    ctx.ellipse(fnPt.x, fnPt.y, rx2, ry2, 0, 0, Math.PI, false);
    ctx.closePath(); ctx.fill();
    ctx.restore();
  }

  // ---- harbour control tower ------------------------------------------
  function controlTower(ctx, gx, gy, pal, opt, t) {
    opt = opt || {};
    const fl    = opt.flags || {};
    blob(ctx, gx, gy, 1.1, H, 0.16);
    const wall  = mix(pal.building, '#5a6a70', 0.45);
    const glass = mix('#7abcd0', '#b8d8e0', 0.5);

    // Base office block
    isoBox(ctx, gx, gy, 1.3, 1.05, 22, H, wall, { edge: shade(wall, -0.35) });
    drawWindowRow(ctx, gx, gy, 1.3, 1.05, 22, pal, fl);

    // Tower shaft
    isoBox(ctx, gx, gy - 0.1, 0.54, 0.45, 22, H + 22, shade(wall, 0.04));

    // Glass observation cab
    const cabW = 0.76, cabD = 0.64, cabHz = 11, cabBase = H + 44;
    isoBox(ctx, gx, gy - 0.1, cabW, cabD, cabHz, cabBase, shade(wall, -0.06), {
      top:   mix(wall, '#c8d8dc', 0.35),
      left:  withAlpha(glass, 0.72),
      right: withAlpha(mix(glass, '#fff', 0.25), 0.55),
    });
    gableRoof(ctx, gx, gy - 0.1, cabW + 0.16, cabD + 0.14, 6, cabBase + cabHz, shade(wall, -0.18));

    // Antenna mast
    const antB = project(gx, gy - 0.1, cabBase + cabHz + 8);
    const antT = project(gx, gy - 0.1, cabBase + cabHz + 26);
    ctx.strokeStyle = '#3a4a52'; ctx.lineWidth = 1.6;
    ctx.beginPath(); ctx.moveTo(antB.x, antB.y); ctx.lineTo(antT.x, antT.y); ctx.stroke();
    const cb = project(gx, gy - 0.1, cabBase + cabHz + 18);
    ctx.beginPath(); ctx.moveTo(cb.x - 5, cb.y); ctx.lineTo(cb.x + 5, cb.y); ctx.stroke();

    // Blinking navigation light
    const blink = 0.5 + 0.5 * Math.sin((t || 0) / 600);
    ctx.beginPath(); ctx.arc(antT.x, antT.y, 2.8, 0, 6.28);
    ctx.fillStyle = withAlpha('#ff2820', 0.45 + 0.50 * blink); ctx.fill();

    if (fl.snow) snowCap(ctx, gx, gy - 0.1, cabW + 0.16, cabD + 0.14, cabBase + cabHz + 6);
  }

  // ---- refrigerated warehouse -----------------------------------------
  function coldWarehouse(ctx, gx, gy, pal, opt) {
    opt = opt || {};
    const fl    = opt.flags || {};
    blob(ctx, gx, gy, 1.8, H, 0.16);
    const wall  = mix('#cdd8de', pal.sandDark, 0.14);
    const roofC = mix('#5a7888', '#3a5060', 0.5);
    const doorC = mix('#4a9aaa', '#1a6878', 0.4);

    isoBox(ctx, gx, gy, 2.4, 1.5, 15, H, wall, {
      top: mix(wall, '#fff', 0.14), left: shade(wall, -0.22),
      right: shade(wall, -0.10), edge: shade(wall, -0.35)
    });
    // Flat roof
    const rA = project(gx-1.2, gy-0.75, H+15), rB = project(gx+1.2, gy-0.75, H+15);
    const rC = project(gx+1.2, gy+0.75, H+15), rD = project(gx-1.2, gy+0.75, H+15);
    poly(ctx, [rA, rB, rC, rD], mix(roofC, '#fff', 0.12), shade(roofC, -0.22), 1);

    // Refrigeration units on roof
    for (const [dx, dy] of [[-0.52, -0.10], [0.52, 0.10], [0.0, 0.42]]) {
      isoBox(ctx, gx+dx, gy+dy, 0.50, 0.34, 6, H+15, shade(roofC, -0.08));
      const fanC = project(gx+dx, gy+dy, H+21);
      ctx.beginPath(); ctx.arc(fanC.x, fanC.y, 5.5, 0, 6.28); ctx.fillStyle = shade(roofC,-0.28); ctx.fill();
      ctx.beginPath(); ctx.arc(fanC.x, fanC.y, 2.5, 0, 6.28); ctx.fillStyle = shade(roofC, 0.12); ctx.fill();
    }
    // Insulated roller doors (blue tint)
    for (const du of [-0.45, 0.45]) {
      const dp = project(gx+1.2, gy+du, H+7);
      ctx.save(); ctx.translate(dp.x, dp.y); ctx.transform(1, 0.5, 0, 1, 0, 0);
      ctx.fillStyle = doorC; ctx.fillRect(-8.5, -10, 17, 13);
      ctx.strokeStyle = withAlpha(mix(doorC,'#fff',0.4), 0.8); ctx.lineWidth = 1.2;
      for (let r = 0; r < 3; r++) { ctx.beginPath(); ctx.moveTo(-8.5,-10+r*4.5); ctx.lineTo(8.5,-10+r*4.5); ctx.stroke(); }
      ctx.restore();
    }
    if (fl.snow) snowCap2(ctx, gx, gy, 2.4, 1.5, H+15);
  }

  // ---- heavy articulated truck ----------------------------------------
  function heavyTruck(ctx, gx, gy, pal, opt) {
    opt = opt || {};
    blob(ctx, gx, gy, 1.0, H, 0.18);
    const cab     = mix(pal.building, '#7a8a90', 0.55);
    const trailer = mix('#ccc8be', pal.sandDark, 0.18);

    // Trailer (positive gx side)
    isoBox(ctx, gx+0.62, gy, 1.0, 0.56, 13, H+2, trailer, {
      top: shade(trailer,0.10), left: shade(trailer,-0.22), right: shade(trailer,-0.10)
    });
    for (const [dx, dy] of [[0.42,0.30],[0.42,-0.30],[0.80,0.30],[0.80,-0.30]])
      wheel(ctx, gx+dx, gy+dy, 4.2);
    // Safety stripe on rear
    const tbR = project(gx+1.12, gy, H+7);
    ctx.save(); ctx.translate(tbR.x, tbR.y); ctx.transform(1, 0.5, 0, 1, 0, 0);
    ctx.fillStyle = withAlpha(mix(pal.roofWarm,'#f0e020',0.5), 0.8);
    for (let i = 0; i < 4; i++) ctx.fillRect(-16+i*9, -4, 5, 8);
    ctx.restore();

    // Cab
    isoBox(ctx, gx-0.44, gy, 0.56, 0.52, 16, H+2, cab, {
      top: shade(cab,0.10), left: shade(cab,-0.25), right: shade(cab,-0.12)
    });
    const cws = project(gx-0.44, gy+0.28, H+9);
    ctx.save(); ctx.translate(cws.x, cws.y); ctx.transform(1,-0.5,0,1,0,0);
    ctx.fillStyle = withAlpha('#bfe0e4',0.85); ctx.fillRect(-5,-9,11,9); ctx.restore();
    for (const [dx, dy] of [[-0.60,0.28],[-0.60,-0.28],[-0.26,0.28],[-0.26,-0.28]])
      wheel(ctx, gx+dx, gy+dy, 5);
    // Exhaust stack
    const ex = project(gx-0.64, gy-0.26, H+16);
    ctx.strokeStyle = '#2a3038'; ctx.lineWidth = 2.2;
    ctx.beginPath(); ctx.moveTo(ex.x, ex.y); ctx.lineTo(ex.x, ex.y-10); ctx.stroke();
  }

  // ---- helipad --------------------------------------------------------
  function helipad(ctx, gx, gy, pal, opt, t) {
    opt = opt || {};
    const padH = H + 1;
    const corners = [
      project(gx-1.0, gy-1.0, padH), project(gx+1.0, gy-1.0, padH),
      project(gx+1.0, gy+1.0, padH), project(gx-1.0, gy+1.0, padH),
    ];
    poly(ctx, corners, mix(pal.sand,'#aaa8a0',0.55), shade(pal.sand,-0.30), 1);

    const cPt = project(gx, gy, padH);

    // Circle marking
    ctx.save(); ctx.strokeStyle = withAlpha('#f0d820',0.85); ctx.lineWidth = 2.5;
    ctx.beginPath(); ctx.ellipse(cPt.x, cPt.y, 0.82*TILE, 0.82*QUART, 0, 0, 6.28); ctx.stroke();
    ctx.restore();

    // H marking drawn in iso space
    ctx.save(); ctx.strokeStyle = withAlpha('#f0d820',0.80); ctx.lineWidth = 4; ctx.lineCap = 'round';
    const hLT = project(gx-0.24, gy,       padH+0.5), hLB = project(gx-0.24, gy+0.42, padH+0.5);
    const hRT = project(gx+0.24, gy,        padH+0.5), hRB = project(gx+0.24, gy+0.42, padH+0.5);
    const hCL = project(gx-0.24, gy+0.21,  padH+0.5), hCR = project(gx+0.24, gy+0.21, padH+0.5);
    ctx.beginPath(); ctx.moveTo(hLT.x,hLT.y); ctx.lineTo(hLB.x,hLB.y); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(hRT.x,hRT.y); ctx.lineTo(hRB.x,hRB.y); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(hCL.x,hCL.y); ctx.lineTo(hCR.x,hCR.y); ctx.stroke();
    ctx.restore();

    // Corner landing lights (blinking)
    const blink = 0.5 + 0.5 * Math.sin((t||0)/700);
    for (const [dx, dy] of [[-0.78,-0.78],[0.78,-0.78],[0.78,0.78],[-0.78,0.78]]) {
      const lp = project(gx+dx, gy+dy, padH+1.5);
      ctx.beginPath(); ctx.arc(lp.x, lp.y, 3.0, 0, 6.28);
      ctx.fillStyle = withAlpha('#ff3820', 0.38+0.58*blink); ctx.fill();
    }
  }

  global.Sprites = {
    tree, pine, bush, rocks, lighthouse, windmill, farmhouse, barn, silo,
    packhouse, stall, dock, fishingBoat, fishPen, cattle, tractor, combine, pickup,
    warehouse, kitchenCottage,
    mountain, mineEntrance, oilDerrick, crusher, oreHeap, smelter, refinery, dumpTruck, supplyBoat,
    portCrane, forklift, containerStack, cargoShip, tugboat, controlTower, coldWarehouse, heavyTruck, helipad,
  };
})(window);
