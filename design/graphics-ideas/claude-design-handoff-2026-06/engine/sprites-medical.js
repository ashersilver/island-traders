/* ============================================================
   sprites-medical.js — Healthcare & Research sprites
   Extends global.Sprites with:
     hospitalBlock, researchDome, satelliteDish, medClinic
   ============================================================ */
(function (global) {
  'use strict';
  const Iso = global.Iso;
  const { project, isoBox, isoCylinder, poly, blob,
          shade, mix, withAlpha,
          drawWindowRow, snowCap, TILE, QUART } = Iso;
  const H = global.Island.LANDH;

  // ---- hospitalBlock — multi-story hospital with roof cross ----------
  function hospitalBlock(ctx, gx, gy, pal, opt) {
    opt = opt || {};
    const fl   = opt.flags || {};
    const s    = opt.scale || 1;
    blob(ctx, gx, gy, 1.7 * s, H, 0.18);
    const wall  = mix('#b4c8d0', '#c4d8e0', 0.5);
    const roofC = mix('#3e6878', '#2e5868', 0.5);

    // Main 3-storey block
    isoBox(ctx, gx, gy, 2.2 * s, 1.5 * s, 30, H, wall, {
      top: mix(wall, '#fff', 0.14), left: shade(wall, -0.18),
      right: shade(wall, -0.07), edge: shade(wall, -0.32)
    });
    drawWindowRow(ctx, gx, gy, 2.2 * s, 1.5 * s, 30, pal, fl);

    // Flat teal roof
    const r0 = project(gx - 1.1*s, gy - 0.75*s, H+30);
    const r1 = project(gx + 1.1*s, gy - 0.75*s, H+30);
    const r2 = project(gx + 1.1*s, gy + 0.75*s, H+30);
    const r3 = project(gx - 1.1*s, gy + 0.75*s, H+30);
    poly(ctx, [r0, r1, r2, r3], roofC, shade(roofC, -0.20), 1);

    // Red cross on roof (iso face projection)
    const crPt = project(gx - 0.25*s, gy, H + 30.5);
    ctx.save(); ctx.translate(crPt.x, crPt.y); ctx.transform(1, -0.5, 0, 1, 0, 0);
    ctx.fillStyle = '#d02020';
    ctx.fillRect(-3, -11, 6, 22); ctx.fillRect(-11, -3, 22, 6);
    ctx.restore();

    // White H marking on roof
    const hPt = project(gx + 0.40*s, gy + 0.20*s, H + 30.5);
    ctx.save(); ctx.translate(hPt.x, hPt.y); ctx.transform(1, -0.5, 0, 1, 0, 0);
    ctx.fillStyle = withAlpha('#ffffff', 0.80);
    ctx.fillRect(-4, -8, 3, 16);
    ctx.fillRect( 1, -8, 3, 16);
    ctx.fillRect(-4, -1.5, 9, 3);
    ctx.restore();

    // Entrance canopy
    isoBox(ctx, gx + 1.1*s, gy, 0.10, 0.70*s, 4, H + 5, mix(wall, '#fff', 0.22));

    if (fl.snow) snowCap(ctx, gx, gy, 2.2 * s, 1.5 * s, H + 30);
  }

  // ---- researchDome — geodesic dome research centre -----------------
  function researchDome(ctx, gx, gy, pal, opt, t) {
    opt = opt || {};
    const fl  = opt.flags || {};
    const s   = opt.scale || 1;
    blob(ctx, gx, gy, 0.98 * s, H, 0.15);
    const base  = mix('#7a9ca4', '#8aacb4', 0.5);
    const domeC = mix('#b8d0d8', '#c8e0e8', 0.45);

    // Base building annex
    isoBox(ctx, gx, gy, 1.5 * s, 1.3 * s, 10, H, base, {
      top: mix(base, '#c8d8dc', 0.20), left: shade(base, -0.22), right: shade(base, -0.08)
    });
    drawWindowRow(ctx, gx, gy, 1.5 * s, 1.3 * s, 10, pal, fl);

    // Geodesic hemisphere: stacked ellipses bottom→top
    // At frac=0: full radius, at equator; frac=1: zero radius, at apex
    const domeR = 0.68 * s;
    const dBase = H + 10;
    const domeH = 20 * s;
    const N     = 10;
    for (let i = 0; i <= N; i++) {
      const frac = i / N;                                      // 0 = equator, 1 = top
      const r    = domeR * Math.cos(frac * Math.PI / 2);     // domeR → 0
      const hh   = domeH * Math.sin(frac * Math.PI / 2);     // 0 → domeH
      if (r * TILE < 1) continue;
      const col  = shade(domeC, -0.10 + frac * 0.24);        // darker at base, lighter at top
      const dPt  = project(gx, gy, dBase + hh);
      const drx  = r * TILE, dry = r * QUART;
      ctx.save();
      ctx.fillStyle = col;
      ctx.beginPath(); ctx.ellipse(dPt.x, dPt.y, drx, dry, 0, 0, Math.PI * 2); ctx.fill();
      // Geodesic ring lines every 3 tiers
      if (i % 3 === 0 && drx > 2.5) {
        ctx.strokeStyle = withAlpha(shade(domeC, -0.14), 0.38); ctx.lineWidth = 0.7;
        ctx.beginPath(); ctx.ellipse(dPt.x, dPt.y, drx, dry, 0, 0, Math.PI * 2); ctx.stroke();
      }
      ctx.restore();
    }
    // Apex cap
    const apexPt = project(gx, gy, dBase + domeH);
    ctx.fillStyle = mix(domeC, '#ffffff', 0.35);
    ctx.beginPath(); ctx.arc(apexPt.x, apexPt.y, 2.8, 0, 6.28); ctx.fill();
  }

  // ---- satelliteDish — parabolic research dish ----------------------
  function satelliteDish(ctx, gx, gy, pal, opt, t) {
    opt = opt || {};
    const s     = opt.scale || 1;
    const metal = '#6a7a80';
    const dish  = mix('#c4c8c4', '#b8bcb8', 0.5);

    // Mount post
    isoBox(ctx, gx, gy, 0.06 * s, 0.06 * s, 12 * s, H, metal);

    // Pivot arm
    const armH  = H + 12 * s;
    const aBase = project(gx, gy, armH);
    const aTip  = project(gx + 0.22 * s, gy - 0.18 * s, armH + 5 * s);
    ctx.save(); ctx.strokeStyle = metal; ctx.lineWidth = 1.6;
    ctx.beginPath(); ctx.moveTo(aBase.x, aBase.y); ctx.lineTo(aTip.x, aTip.y); ctx.stroke(); ctx.restore();

    // Dish (slow animated tilt)
    const tilt = Math.sin((t || 0) / 3800) * 0.06 * s;
    const dPt  = project(gx + 0.22 * s + tilt, gy - 0.18 * s, armH + 6 * s);
    const drx  = 0.26 * s * TILE, dry = 0.26 * s * QUART;
    ctx.save();
    ctx.fillStyle = dish;
    ctx.beginPath(); ctx.ellipse(dPt.x, dPt.y, drx, dry, 0, 0, Math.PI * 2); ctx.fill();
    ctx.strokeStyle = shade(dish, -0.22); ctx.lineWidth = 0.9;
    ctx.beginPath(); ctx.ellipse(dPt.x, dPt.y, drx, dry, 0, 0, Math.PI * 2); ctx.stroke();
    // Spoke grid
    for (let j = 0; j < 4; j++) {
      const a = (j / 4) * Math.PI;
      ctx.strokeStyle = withAlpha(shade(dish, -0.18), 0.55); ctx.lineWidth = 0.7;
      ctx.beginPath(); ctx.moveTo(dPt.x, dPt.y);
      ctx.lineTo(dPt.x + Math.cos(a) * drx, dPt.y + Math.sin(a) * dry); ctx.stroke();
    }
    // Centre feed
    ctx.fillStyle = metal;
    ctx.beginPath(); ctx.arc(dPt.x, dPt.y, 2.5, 0, 6.28); ctx.fill();
    ctx.restore();
  }

  // ---- medClinic — small annex clinic with cross -------------------
  function medClinic(ctx, gx, gy, pal, opt) {
    opt = opt || {};
    const fl   = opt.flags || {};
    const s    = opt.scale || 1;
    blob(ctx, gx, gy, 0.85 * s, H, 0.14);
    const wall  = mix('#ccd8de', '#d8e4e8', 0.5);
    const roofC = mix('#3e6878', '#2e5868', 0.5);

    isoBox(ctx, gx, gy, 1.2 * s, 0.95 * s, 16, H, wall, {
      top: mix(wall, '#fff', 0.18), left: shade(wall, -0.18),
      right: shade(wall, -0.07), edge: shade(wall, -0.30)
    });
    drawWindowRow(ctx, gx, gy, 1.2 * s, 0.95 * s, 16, pal, fl);

    // Flat teal roof
    const r0 = project(gx - 0.6*s, gy - 0.475*s, H+16);
    const r1 = project(gx + 0.6*s, gy - 0.475*s, H+16);
    const r2 = project(gx + 0.6*s, gy + 0.475*s, H+16);
    const r3 = project(gx - 0.6*s, gy + 0.475*s, H+16);
    poly(ctx, [r0, r1, r2, r3], roofC, shade(roofC, -0.20), 1);

    // Red cross on roof
    const crPt = project(gx, gy, H + 16.5);
    ctx.save(); ctx.translate(crPt.x, crPt.y); ctx.transform(1, -0.5, 0, 1, 0, 0);
    ctx.fillStyle = '#d82020';
    ctx.fillRect(-2.5, -8.5, 5, 17); ctx.fillRect(-8.5, -2.5, 17, 5);
    ctx.restore();

    // Blue entrance door
    const entPt = project(gx + 0.60*s, gy, H + 4);
    ctx.save(); ctx.translate(entPt.x, entPt.y); ctx.transform(1, 0.5, 0, 1, 0, 0);
    ctx.fillStyle = withAlpha(mix(wall, '#4a9ac0', 0.45), 0.88);
    ctx.fillRect(-5, -11, 10, 13);
    ctx.restore();

    if (fl.snow) snowCap(ctx, gx, gy, 1.2 * s, 0.95 * s, H + 16);
  }

  Object.assign(global.Sprites, { hospitalBlock, researchDome, satelliteDish, medClinic });
})(window);
