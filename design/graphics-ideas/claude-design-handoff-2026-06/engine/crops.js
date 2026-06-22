/* ============================================================
   crops.js — Productive land: grain, corn, vegetable beds, pasture.
   Responds to season (stage), drought, flood, snow.
   Field = axis-aligned rect in ground space {gx,gy,w,h}.
   ============================================================ */
(function (global) {
  'use strict';
  const I = global.Iso;
  const { project, shade, mix, withAlpha } = I;
  const H = global.Island.LANDH;

  function rectPts(f, e) {
    const hx = f.w / 2, hy = f.h / 2;
    return [
      project(f.gx - hx, f.gy - hy, e),
      project(f.gx + hx, f.gy - hy, e),
      project(f.gx + hx, f.gy + hy, e),
      project(f.gx - hx, f.gy + hy, e),
    ];
  }

  function fillRect(ctx, pts, color, stroke) {
    ctx.beginPath(); ctx.moveTo(pts[0].x, pts[0].y);
    for (let i = 1; i < 4; i++) ctx.lineTo(pts[i].x, pts[i].y);
    ctx.closePath(); ctx.fillStyle = color; ctx.fill();
    if (stroke) { ctx.strokeStyle = stroke; ctx.lineWidth = 1; ctx.stroke(); }
  }

  // soil tone by season/weather
  function soilTone(pal, flags) {
    let s = '#7a5c39';
    if (flags.drought) s = mix(s, '#a98850', 0.45);
    if (flags.snow) s = mix(s, '#dde4e4', 0.6);
    if (flags.flood) s = mix(s, '#5b6a64', 0.4);
    return s;
  }

  function drawField(ctx, f, pal, flags, t) {
    const e = H + 0.5;
    const pts = rectPts(f, e);
    const kind = f.kind || 'grain';
    const stage = flags.cropStage == null ? 0.7 : flags.cropStage;

    // base soil
    fillRect(ctx, pts, soilTone(pal, flags), withAlpha('#3a2a18', 0.35));

    ctx.save();
    fillRect(ctx, pts); ctx.clip();

    const rng = I.makeRNG((f.seed || 1) * 53 + 11);
    const hx = f.w / 2, hy = f.h / 2;
    const rows = Math.max(3, Math.round(f.h / 0.34));

    if (kind === 'pasture') {
      // just lush grass tufts; cattle drawn separately
      for (let i = 0; i < 60; i++) {
        const x = f.gx - hx + rng() * f.w, y = f.gy - hy + rng() * f.h;
        const p = project(x, y, e);
        ctx.strokeStyle = withAlpha(flags.snow ? '#cfe0d8' : pal.grass, 0.5);
        ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(p.x, p.y); ctx.lineTo(p.x, p.y - 3); ctx.stroke();
      }
      ctx.restore();
      fence(ctx, f, pal);
      return;
    }

    for (let r = 0; r < rows; r++) {
      const gy = f.gy - hy + (r + 0.5) * (f.h / rows);
      const a = project(f.gx - hx, gy, e), b = project(f.gx + hx, gy, e);
      // furrow line
      ctx.strokeStyle = withAlpha('#4a3520', 0.35); ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();

      if (flags.bare && kind !== 'orchard') {
        // winter stubble only
        continue;
      }
      // crop marks along the row
      const perRow = Math.max(4, Math.round(f.w / 0.28));
      for (let c = 0; c < perRow; c++) {
        const gx = f.gx - hx + (c + 0.5) * (f.w / perRow) + (rng() - 0.5) * 0.05;
        const p = project(gx, gy, e);
        drawCrop(ctx, p, kind, stage, flags, pal, rng);
      }
    }
    ctx.restore();

    // harvested swath in autumn for grain
    if (kind === 'grain' && flags.harvest) {
      ctx.save(); fillRect(ctx, pts); ctx.clip();
      const cut = project(f.gx, f.gy + hy * 0.2, e);
      ctx.fillStyle = withAlpha('#cbb274', 0.5);
      ctx.fillRect(cut.x - 60, cut.y - 4, 120, 30);
      ctx.restore();
    }
  }

  function drawCrop(ctx, p, kind, stage, flags, pal, rng) {
    if (kind === 'corn') {
      const hgt = (flags.bare ? 2 : 4 + stage * 9);
      const col = flags.drought ? mix('#9aa54e', '#b89a4e', 0.6) : (flags.harvest ? '#c9a23e' : mix('#6f9b3e', '#9bc24f', 1 - stage));
      ctx.strokeStyle = flags.snow ? '#cfe0d8' : col; ctx.lineWidth = 1.4;
      ctx.beginPath(); ctx.moveTo(p.x, p.y); ctx.lineTo(p.x - 1, p.y - hgt); ctx.stroke();
      // leaves
      if (!flags.bare) { ctx.strokeStyle = withAlpha(col, 0.8); ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(p.x - 1, p.y - hgt * 0.6); ctx.lineTo(p.x + 3, p.y - hgt * 0.6 - 2); ctx.moveTo(p.x - 1, p.y - hgt * 0.45); ctx.lineTo(p.x - 4, p.y - hgt * 0.45 - 1); ctx.stroke(); }
      return;
    }
    if (kind === 'veg') {
      const r = 1.6 + stage * 1.3;
      let col = flags.drought ? '#9a9a52' : mix('#5f8a3e', '#7fb04e', stage);
      if (flags.snow) col = '#d6e2e0';
      ctx.fillStyle = col; ctx.beginPath(); ctx.ellipse(p.x, p.y - r * 0.5, r, r * 0.7, 0, 0, 6.28); ctx.fill();
      // row of cabbages tint
      ctx.fillStyle = withAlpha('#3f5a26', 0.4); ctx.beginPath(); ctx.arc(p.x, p.y - r * 0.5, r * 0.4, 0, 6.28); ctx.fill();
      return;
    }
    // grain (default): little upright strokes, golden when ripe
    const hgt = flags.bare ? 1.5 : 3 + stage * 4;
    let col;
    if (flags.snow) col = '#d9e4e2';
    else if (flags.drought) col = mix('#b89a4e', '#cbb05a', rng());
    else col = stage > 0.8 ? pal.crop : mix(pal.cropYoung || '#7faa4c', pal.crop, stage);
    ctx.strokeStyle = withAlpha(col, 0.9); ctx.lineWidth = 1.2;
    ctx.beginPath(); ctx.moveTo(p.x, p.y); ctx.lineTo(p.x, p.y - hgt); ctx.stroke();
    if (stage > 0.6 && !flags.snow) { ctx.fillStyle = col; ctx.beginPath(); ctx.arc(p.x, p.y - hgt, 1, 0, 6.28); ctx.fill(); }
  }

  function fence(ctx, f, pal) {
    const hx = f.w / 2, hy = f.h / 2, e = H + 0.5;
    const corners = [[-hx, -hy], [hx, -hy], [hx, hy], [-hx, hy]];
    ctx.strokeStyle = pal.woodDockDark; ctx.lineWidth = 1.4;
    for (let i = 0; i < 4; i++) {
      const a = corners[i], b = corners[(i + 1) % 4];
      const steps = 6;
      for (let s = 0; s <= steps; s++) {
        const gx = f.gx + a[0] + (b[0] - a[0]) * s / steps;
        const gy = f.gy + a[1] + (b[1] - a[1]) * s / steps;
        const p = project(gx, gy, e);
        ctx.beginPath(); ctx.moveTo(p.x, p.y); ctx.lineTo(p.x, p.y - 7); ctx.stroke();
      }
      const pa = project(f.gx + a[0], f.gy + a[1], e + 0), pb = project(f.gx + b[0], f.gy + b[1], e);
      ctx.beginPath(); ctx.moveTo(pa.x, pa.y - 5); ctx.lineTo(pb.x, pb.y - 5); ctx.stroke();
    }
  }

  global.Crops = { drawField };
})(window);
