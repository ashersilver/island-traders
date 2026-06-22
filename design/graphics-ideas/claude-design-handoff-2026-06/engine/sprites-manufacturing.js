/* ============================================================
   sprites-manufacturing.js — Manufacturing & Industry sprites
   Extends global.Sprites with:
     factory, smokestack, coolingTower, assemblyPlant
   ============================================================ */
(function (global) {
  'use strict';
  const Iso = global.Iso;
  const { project, isoBox, isoCylinder, poly, blob,
          shade, mix, withAlpha,
          drawWindowRow, snowCap, TILE, QUART } = Iso;
  const H = global.Island.LANDH;

  // ---- factory -------------------------------------------------------
  function factory(ctx, gx, gy, pal, opt, t) {
    opt = opt || {};
    const fl   = opt.flags || {};
    const s    = opt.scale || 1;
    blob(ctx, gx, gy, 1.6 * s, H, 0.18);
    const wall  = mix('#2a3c44', '#384e58', 0.5);
    const wallB = shade(wall, 0.06);
    const acc   = '#4a7888';

    // Main production hall — wide, multi-story
    isoBox(ctx, gx, gy, 2.0 * s, 1.4 * s, 24, H, wall, {
      top: shade(wall, 0.08), left: shade(wall, -0.22),
      right: shade(wall, -0.09), edge: shade(wall, -0.40)
    });
    drawWindowRow(ctx, gx, gy, 2.0 * s, 1.4 * s, 24, pal, fl);

    // Side annex (lower)
    isoBox(ctx, gx + 1.1 * s, gy - 0.2 * s, 0.8 * s, 0.9 * s, 15, H, wallB, {
      top: shade(wallB, 0.06), left: shade(wallB, -0.20), right: shade(wallB, -0.08)
    });
    drawWindowRow(ctx, gx + 1.1 * s, gy - 0.2 * s, 0.8 * s, 0.9 * s, 15, pal, fl);

    // Roof plant boxes
    isoBox(ctx, gx - 0.4 * s, gy - 0.2 * s, 0.55 * s, 0.34 * s, 5, H + 24, shade(wall, -0.05));
    isoBox(ctx, gx + 0.4 * s, gy + 0.2 * s, 0.38 * s, 0.28 * s, 4, H + 24, acc);

    // Overhead pipe connecting buildings
    const p0 = project(gx, gy - 0.70 * s, H + 20);
    const p1 = project(gx + 1.55 * s, gy - 0.70 * s, H + 20);
    ctx.save(); ctx.strokeStyle = shade(wall, 0.15); ctx.lineWidth = 4.0;
    ctx.beginPath(); ctx.moveTo(p0.x, p0.y); ctx.lineTo(p1.x, p1.y); ctx.stroke(); ctx.restore();

    // Industrial roller door on right face
    const dPt = project(gx + 1.0 * s, gy + 0.3 * s, H + 5);
    ctx.save(); ctx.translate(dPt.x, dPt.y); ctx.transform(1, 0.5, 0, 1, 0, 0);
    ctx.fillStyle = withAlpha(mix(acc, '#1a2a30', 0.4), 0.88); ctx.fillRect(-14, -16, 28, 18);
    ctx.strokeStyle = shade(wall, -0.15); ctx.lineWidth = 1.2;
    ctx.beginPath(); ctx.moveTo(0, -16); ctx.lineTo(0, 2); ctx.stroke();
    ctx.restore();

    if (fl.snow) snowCap(ctx, gx, gy, 2.0 * s, 1.4 * s, H + 24);
  }

  // ---- smokestack with animated smoke --------------------------------
  function smokestack(ctx, gx, gy, pal, opt, t) {
    opt = opt || {};
    const s      = opt.scale || 1;
    const brick  = mix('#7a4a38', '#8a5848', 0.5);
    const brickD = shade(brick, -0.26);

    blob(ctx, gx, gy, 0.26 * s, H, 0.12);
    // Base collar
    isoBox(ctx, gx, gy, 0.28 * s, 0.28 * s, 4, H, shade(brick, -0.12));
    // Shaft
    isoCylinder(ctx, gx, gy, 0.20 * s, 52, H + 4, brick, { top: brickD });
    isoCylinder(ctx, gx, gy, 0.16 * s, 8,  H + 56, shade(brick, -0.12), { top: brickD });

    // Mortar bands
    ctx.save(); ctx.strokeStyle = withAlpha(shade(brick, 0.18), 0.55); ctx.lineWidth = 1.3;
    for (let bh = 16; bh < 58; bh += 20) {
      const bPt = project(gx, gy, H + 4 + bh);
      ctx.beginPath(); ctx.ellipse(bPt.x, bPt.y, 0.20 * s * TILE, 0.20 * s * QUART, 0, 0, Math.PI * 2); ctx.stroke();
    }
    ctx.restore();

    // Rim cap with dark interior
    const rPt = project(gx, gy, H + 64);
    ctx.save();
    ctx.fillStyle = brickD;
    ctx.beginPath(); ctx.ellipse(rPt.x, rPt.y, 0.20 * s * TILE + 2, 0.20 * s * QUART + 1, 0, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = withAlpha('#1a1814', 0.75);
    ctx.beginPath(); ctx.ellipse(rPt.x, rPt.y, 0.20 * s * TILE - 1, 0.20 * s * QUART - 0.5, 0, 0, Math.PI * 2); ctx.fill();
    ctx.restore();

    // Animated smoke puffs
    for (let i = 0; i < 6; i++) {
      const phase  = ((t || 0) * 0.00028 + i / 6) % 1;
      const spread = phase * 0.30 * s;
      const pPt    = project(gx + Math.sin(i * 2.1) * spread, gy + Math.cos(i * 1.7) * spread * 0.5, H + 64 + phase * 36);
      const r      = (3 + phase * 13) * s;
      ctx.beginPath(); ctx.arc(pPt.x, pPt.y, r, 0, 6.28);
      ctx.fillStyle = withAlpha('#c4c0ba', 0.48 * (1 - phase * 0.85)); ctx.fill();
    }
  }

  // ---- cooling tower (hyperbolic profile) ----------------------------
  function coolingTower(ctx, gx, gy, pal, opt, t) {
    opt = opt || {};
    const s        = opt.scale || 1;
    const concrete = mix('#9c9a88', '#b0ae9c', 0.5);
    const inner    = shade(concrete, -0.38);

    blob(ctx, gx, gy, 0.65 * s, H, 0.14);
    // Wide base → narrow waist → slight top flare
    isoCylinder(ctx, gx, gy, 0.58 * s, 18, H,      concrete);
    isoCylinder(ctx, gx, gy, 0.40 * s, 14, H + 18, shade(concrete, 0.04));
    isoCylinder(ctx, gx, gy, 0.46 * s,  8, H + 32, shade(concrete, 0.04), { top: inner });

    // Dark interior opening
    const topPt = project(gx, gy, H + 40);
    ctx.save(); ctx.fillStyle = withAlpha('#1c2830', 0.82);
    ctx.beginPath(); ctx.ellipse(topPt.x, topPt.y, 0.38 * s * TILE, 0.38 * s * QUART, 0, 0, Math.PI * 2); ctx.fill();
    ctx.restore();

    // Animated steam puffs (lighter/whiter than smokestack)
    for (let i = 0; i < 5; i++) {
      const phase  = ((t || 0) * 0.00022 + i * 0.2) % 1;
      const spread = phase * 0.26 * s;
      const pPt    = project(gx + Math.sin(i * 2.3) * spread, gy + Math.cos(i * 1.5) * spread * 0.5, H + 40 + phase * 28);
      const r      = (4 + phase * 14) * s;
      ctx.beginPath(); ctx.arc(pPt.x, pPt.y, r, 0, 6.28);
      ctx.fillStyle = withAlpha('#e8e4de', 0.55 * (1 - phase * 0.90)); ctx.fill();
    }
  }

  // ---- assembly plant (sawtooth roof) --------------------------------
  function assemblyPlant(ctx, gx, gy, pal, opt) {
    opt = opt || {};
    const fl   = opt.flags || {};
    const s    = opt.scale || 1;
    blob(ctx, gx, gy, 1.35 * s, H, 0.16);
    const wall  = mix('#3e5460', '#4c6472', 0.5);
    const roofC = shade(wall, -0.06);
    const skyBl = withAlpha(mix('#bfe0e4', '#d8ecf0', 0.5), 0.72);

    isoBox(ctx, gx, gy, 2.1 * s, 1.2 * s, 12, H, wall, {
      top: shade(wall, 0.07), left: shade(wall, -0.22),
      right: shade(wall, -0.10), edge: shade(wall, -0.38)
    });
    drawWindowRow(ctx, gx, gy, 2.1 * s, 1.2 * s, 12, pal, fl);

    // Sawtooth roof bays with north-light skylights
    for (let i = 0; i < 3; i++) {
      const rx = gx + (-0.7 + i * 0.7) * s;
      isoBox(ctx, rx, gy, 0.52 * s, 1.18 * s, 5, H + 12, roofC);
      const slPt = project(rx, gy - 0.55 * s, H + 17);
      ctx.save(); ctx.translate(slPt.x, slPt.y); ctx.transform(1, -0.5, 0, 1, 0, 0);
      ctx.fillStyle = skyBl; ctx.fillRect(-7, -4, 14, 5.5); ctx.restore();
    }

    // Loading dock on right face
    const ldPt = project(gx + 1.05 * s, gy + 0.2 * s, H + 5);
    ctx.save(); ctx.translate(ldPt.x, ldPt.y); ctx.transform(1, 0.5, 0, 1, 0, 0);
    ctx.fillStyle = shade(wall, -0.18); ctx.fillRect(-11, -14, 22, 16);
    ctx.strokeStyle = shade(wall, -0.32); ctx.lineWidth = 0.9;
    for (let r = 0; r < 3; r++) { ctx.beginPath(); ctx.moveTo(-11, -14 + r * 4.8); ctx.lineTo(11, -14 + r * 4.8); ctx.stroke(); }
    ctx.restore();

    if (fl.snow) snowCap(ctx, gx, gy, 2.1 * s, 1.2 * s, H + 12);
  }

  Object.assign(global.Sprites, { factory, smokestack, coolingTower, assemblyPlant });
})(window);
