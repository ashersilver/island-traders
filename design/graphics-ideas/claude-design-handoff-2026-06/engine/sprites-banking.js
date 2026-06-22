/* ============================================================
   sprites-banking.js — Banking & Insurance sprites
   Extends global.Sprites with:
     bankBuilding, officeTower, ornamentalPond
   ============================================================ */
(function (global) {
  'use strict';
  const Iso = global.Iso;
  const { project, isoBox, isoCylinder, poly, blob,
          shade, mix, withAlpha,
          drawWindowRow, snowCap, TILE, QUART } = Iso;
  const H = global.Island.LANDH;

  // ---- bankBuilding — classical columns & pediment ------------------
  function bankBuilding(ctx, gx, gy, pal, opt) {
    opt = opt || {};
    const fl    = opt.flags || {};
    blob(ctx, gx, gy, 1.4, H, 0.18);
    const stone = mix('#3a3830', '#4a4840', 0.5);
    const cream = mix('#c8b888', '#d8c898', 0.5);
    const gold  = mix('#b88820', '#c89830', 0.5);

    // Grand entrance steps (staggered on right face)
    for (let s = 0; s < 3; s++) {
      isoBox(ctx, gx + 0.85 - s * 0.10, gy, 0.08, 1.5 - s * 0.12, 2, H + s * 2,
        mix(stone, cream, s * 0.12 + 0.08));
    }

    // Main body
    isoBox(ctx, gx, gy, 1.8, 1.3, 25, H, stone, {
      top: mix(stone, cream, 0.16), left: shade(stone, -0.22),
      right: shade(stone, -0.09), edge: shade(stone, -0.42)
    });
    drawWindowRow(ctx, gx, gy, 1.8, 1.3, 25, pal, fl);

    // Classical columns on the street-facing right side
    for (const dy of [-0.44, -0.14, 0.16, 0.46]) {
      isoCylinder(ctx, gx + 0.90, gy + dy, 0.065, 22, H + 1, mix(stone, cream, 0.32));
    }

    // Triangular pediment above columns
    const pL  = project(gx + 0.90, gy - 0.56, H + 26);
    const pR  = project(gx + 0.90, gy + 0.56, H + 26);
    const pTp = project(gx + 0.90, gy + 0.00, H + 39);
    poly(ctx, [pL, pR, pTp], mix(stone, cream, 0.14), shade(stone, -0.28), 1);

    // Cornice ledge
    isoBox(ctx, gx, gy, 1.88, 1.38, 2, H + 25, mix(stone, cream, 0.20));

    // Gold arched entrance door
    const dPt = project(gx + 0.90, gy, H + 3);
    ctx.save(); ctx.translate(dPt.x, dPt.y); ctx.transform(1, 0.5, 0, 1, 0, 0);
    ctx.fillStyle = withAlpha(gold, 0.92); ctx.fillRect(-6, -15, 12, 16);
    ctx.beginPath(); ctx.arc(0, -15, 6, Math.PI, 0);
    ctx.fillStyle = withAlpha(mix(gold, '#c8e4e0', 0.4), 0.85); ctx.fill();
    ctx.restore();

    if (fl.snow) snowCap(ctx, gx, gy, 1.8, 1.3, H + 25);
  }

  // ---- officeTower — stepped modern glass tower ---------------------
  function officeTower(ctx, gx, gy, pal, opt) {
    opt = opt || {};
    const fl    = opt.flags || {};
    blob(ctx, gx, gy, 1.1, H, 0.17);
    const glass = mix('#263843', '#344e5a', 0.5);
    const frame = mix(glass, '#6a8898', 0.30);

    // Base podium
    isoBox(ctx, gx, gy, 1.4, 1.0, 10, H, mix(glass, frame, 0.22), {
      top: mix(glass, frame, 0.38), left: shade(glass, -0.22), right: shade(glass, -0.08)
    });
    drawWindowRow(ctx, gx, gy, 1.4, 1.0, 10, pal, fl);

    // Tower tier 1
    isoBox(ctx, gx - 0.08, gy - 0.06, 1.0, 0.75, 18, H + 10, glass, {
      top: mix(glass, frame, 0.22), left: shade(glass, -0.24), right: shade(glass, -0.10)
    });
    drawWindowRow(ctx, gx - 0.08, gy - 0.06, 1.0, 0.75, 18, pal, fl);

    // Tower tier 2
    isoBox(ctx, gx - 0.18, gy - 0.12, 0.68, 0.52, 16, H + 28, shade(glass, 0.04), {
      top: mix(glass, frame, 0.18), left: shade(glass, -0.22), right: shade(glass, -0.08)
    });
    drawWindowRow(ctx, gx - 0.18, gy - 0.12, 0.68, 0.52, 16, pal, fl);

    // Rooftop plant room + mast
    isoBox(ctx, gx - 0.18, gy - 0.12, 0.35, 0.28, 5, H + 44, frame);
    const antB = project(gx - 0.18, gy - 0.12, H + 49);
    const antT = project(gx - 0.18, gy - 0.12, H + 62);
    ctx.save(); ctx.strokeStyle = frame; ctx.lineWidth = 1.4;
    ctx.beginPath(); ctx.moveTo(antB.x, antB.y); ctx.lineTo(antT.x, antT.y); ctx.stroke(); ctx.restore();

    if (fl.snow) snowCap(ctx, gx, gy, 1.4, 1.0, H + 10);
  }

  // ---- ornamentalPond — decorative pool with lily pads ---------------
  function ornamentalPond(ctx, gx, gy, pal, opt, t) {
    opt = opt || {};
    const sz  = opt.size || 1.0;
    const cPt = project(gx, gy, H + 0.5);
    const wPt = project(gx, gy, H + 1.0);
    const rx  = sz * TILE * 1.10, ry  = sz * QUART * 1.10;
    const wrx = sz * TILE * 0.84, wry = sz * QUART * 0.84;

    ctx.save();
    // Stone surround ring
    ctx.fillStyle = mix('#8a8070', '#7a7060', 0.5);
    ctx.beginPath(); ctx.ellipse(cPt.x, cPt.y, rx, ry, 0, 0, Math.PI * 2); ctx.fill();
    ctx.strokeStyle = shade(mix('#8a8070', '#7a7060', 0.5), -0.24); ctx.lineWidth = 1.2; ctx.stroke();

    // Water surface
    ctx.fillStyle = mix(pal.waterDeep, '#2a5060', 0.42);
    ctx.beginPath(); ctx.ellipse(wPt.x, wPt.y, wrx, wry, 0, 0, Math.PI * 2); ctx.fill();

    // Shimmer ripples
    ctx.strokeStyle = withAlpha(pal.waterShallow || '#88c4cc', 0.28); ctx.lineWidth = 1.0;
    for (let i = 0; i < 3; i++) {
      const yOff = Math.sin((t || 0) / 700 + i * 2) * wry * 0.28;
      ctx.beginPath(); ctx.ellipse(wPt.x, wPt.y + yOff, wrx * 0.54, wry * 0.32, 0, 0, Math.PI * 2); ctx.stroke();
    }

    // Lily pads (seeded, deterministic)
    const rng = Iso.makeRNG(77);
    for (let i = 0; i < 7; i++) {
      const a  = rng() * Math.PI * 2, r = 0.15 + rng() * 0.52;
      const lPt = project(gx + Math.cos(a) * r * sz, gy + Math.sin(a) * r * sz * 0.5, H + 1.5);
      const lpr = 4.5 + rng() * 3.5;
      ctx.fillStyle = withAlpha(mix('#1e6018', '#2a7820', rng()), 0.82);
      ctx.beginPath(); ctx.arc(lPt.x, lPt.y, lpr, 0, Math.PI * 2); ctx.fill();
      // Small water-lily flower on some pads
      if (rng() > 0.60) {
        ctx.fillStyle = withAlpha('#e8d8b0', 0.85);
        ctx.beginPath(); ctx.arc(lPt.x, lPt.y, 2.0, 0, Math.PI * 2); ctx.fill();
      }
    }

    // Animated fountain glint at centre
    const fPt   = project(gx, gy, H + 1.8);
    const glint = 0.5 + 0.5 * Math.sin((t || 0) / 800);
    ctx.fillStyle = withAlpha('#c8e8f4', 0.20 + 0.16 * glint);
    ctx.beginPath(); ctx.arc(fPt.x, fPt.y, 6 + glint * 3, 0, Math.PI * 2); ctx.fill();
    ctx.restore();
  }

  Object.assign(global.Sprites, { bankBuilding, officeTower, ornamentalPond });
})(window);
