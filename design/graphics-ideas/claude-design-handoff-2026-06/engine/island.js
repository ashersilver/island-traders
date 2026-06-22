/* ============================================================
   island.js — Organic island terrain generation & rendering
   Builds a natural coastline (no plinth / breakwater) and draws
   water, soil cliffs, sandy shore, grass, hills, ponds, fields.
   ============================================================ */
(function (global) {
  'use strict';
  const I = global.Iso;
  const { project, shade, mix, withAlpha, poly, smoothClosedPath } = I;

  const LANDH = 16;        // px elevation of the grass top surface
  const THICK = 8;         // px soil lip at the waterline (natural, thin)
  const COAST_PTS = 84;    // coastline resolution

  // Generate organic island geometry from a seed.
  // shape: {cx, cy, radius, wobble, lobes} controls the silhouette.
  function generate(seed, shape) {
    shape = shape || {};
    const cx = shape.cx || 0, cy = shape.cy || 0;
    const R = shape.radius || 6.6;
    const wobble = shape.wobble == null ? 0.20 : shape.wobble;
    const noise = I.makeAngularNoise(seed, shape.lobes || 5);
    const noise2 = I.makeAngularNoise(seed + 99, 3);

    const ground = [];   // ground-space coastline points {gx,gy,theta,r}
    for (let i = 0; i < COAST_PTS; i++) {
      const theta = (i / COAST_PTS) * Math.PI * 2;
      // squash y a touch so island reads wider than deep (nicer comp)
      const r = R * (1 + wobble * noise(theta) + 0.06 * noise2(theta * 1.7));
      const gx = cx + r * Math.cos(theta);
      const gy = cy + r * Math.sin(theta) * 0.96;
      ground.push({ gx, gy, theta, r });
    }
    return { cx, cy, R, ground, seed };
  }

  // Is a ground point comfortably inside the coast (for placement checks)?
  function isLand(geo, gx, gy, margin) {
    margin = margin || 0.0;
    const dx = gx - geo.cx, dy = (gy - geo.cy) / 0.96;
    const theta = Math.atan2(dy, dx);
    const dist = Math.hypot(dx, dy);
    // sample coast radius near theta
    let nearest = geo.R;
    let best = 1e9;
    for (const p of geo.ground) {
      let d = Math.abs(((p.theta - theta + Math.PI) % (Math.PI * 2)) - Math.PI);
      if (d < best) { best = d; nearest = p.r; }
    }
    return dist < nearest - margin;
  }

  // ---- draw the full terrain base ------------------------------------
  function drawBase(ctx, geo, pal, weather, t) {
    const flood = weather.flood || 0;     // 0..1 water rise
    const topPts = geo.ground.map(p => project(p.gx, p.gy, LANDH));
    const shorePts = geo.ground.map(p => project(p.gx, p.gy, 0));
    const grassInset = geo.ground.map(p => {
      const k = 0.9; // pull grass in from sand rim
      return project(geo.cx + (p.gx - geo.cx) * k, geo.cy + (p.gy - geo.cy) * k, LANDH);
    });

    // --- cast shadow on water ---
    ctx.save();
    ctx.beginPath();
    const sh = geo.ground.map(p => project(p.gx + 0.5, p.gy + 0.7, -2));
    smoothClosedPath(ctx, sh);
    ctx.fillStyle = withAlpha(pal.waterDeep, 0.55);
    ctx.filter = 'blur(6px)';
    ctx.fill();
    ctx.restore();

    // --- soil cliff sides (front-facing only) ---
    for (let i = 0; i < geo.ground.length; i++) {
      const a = geo.ground[i];
      const b = geo.ground[(i + 1) % geo.ground.length];
      const facing = Math.cos(a.theta) + Math.sin(a.theta); // >0 -> front/right
      const front = (Math.sin(a.theta) * 0.7 + 0.3) ; // south-ness
      if ((Math.sin(a.theta)) < -0.55) continue; // skip far-back walls (hidden)
      const tA = project(a.gx, a.gy, LANDH);
      const tB = project(b.gx, b.gy, LANDH);
      const wA = project(a.gx, a.gy, -THICK);
      const wB = project(b.gx, b.gy, -THICK);
      // tone: lit on right/front, dark on left
      const lit = 0.5 + 0.5 * Math.sin(a.theta - 0.6);
      let soil = mix(pal.soilDark, pal.soil, lit);
      poly(ctx, [tA, tB, wB, wA], soil);
    }
    // waterline lip (darker band just under shore)
    for (let i = 0; i < geo.ground.length; i++) {
      const a = geo.ground[i];
      const b = geo.ground[(i + 1) % geo.ground.length];
      if (Math.sin(a.theta) < -0.55) continue;
      const tA = project(a.gx, a.gy, LANDH);
      const tB = project(b.gx, b.gy, LANDH);
      const wA = project(a.gx, a.gy, LANDH - 7);
      const wB = project(b.gx, b.gy, LANDH - 7);
      const lit = 0.5 + 0.5 * Math.sin(a.theta - 0.6);
      poly(ctx, [tA, tB, wB, wA], mix(pal.soilDark, pal.sandDark, lit * 0.6));
    }

    // --- sandy top (whole island surface) ---
    ctx.save();
    smoothClosedPath(ctx, topPts);
    const sandGrad = ctx.createLinearGradient(0, -120, 0, 160);
    sandGrad.addColorStop(0, shade(pal.sand, 0.06));
    sandGrad.addColorStop(1, shade(pal.sand, -0.05));
    ctx.fillStyle = sandGrad;
    ctx.fill();
    ctx.restore();

    // --- grass inset ---
    ctx.save();
    smoothClosedPath(ctx, grassInset);
    ctx.clip();
    smoothClosedPath(ctx, grassInset);
    const gg = ctx.createLinearGradient(0, -140, 0, 180);
    gg.addColorStop(0, shade(pal.grass, 0.08));
    gg.addColorStop(1, shade(pal.grass, -0.10));
    ctx.fillStyle = gg;
    ctx.fill();
    // subtle mottling
    const rng = I.makeRNG(geo.seed + 7);
    for (let i = 0; i < 90; i++) {
      const ang = rng() * Math.PI * 2, rr = rng() * geo.R * 0.85;
      const gp = project(geo.cx + Math.cos(ang) * rr, geo.cy + Math.sin(ang) * rr * 0.96, LANDH);
      ctx.beginPath();
      ctx.ellipse(gp.x, gp.y, 8 + rng() * 14, (8 + rng() * 14) / 2, 0, 0, Math.PI * 2);
      ctx.fillStyle = withAlpha(rng() > 0.5 ? shade(pal.grass, 0.10) : shade(pal.grass, -0.10), 0.28);
      ctx.fill();
    }
    ctx.restore();

    // store rings for later use (flood overlay etc.)
    return { topPts, shorePts, grassInset };
  }

  // foam ring + flood overlay drawn ON TOP of land when flooded
  function drawShoreFoam(ctx, geo, pal, weather, t) {
    const shorePts = geo.ground.map(p => project(p.gx, p.gy, LANDH - 2));
    ctx.save();
    smoothClosedPath(ctx, shorePts);
    ctx.lineWidth = 3.5;
    ctx.strokeStyle = withAlpha(pal.foam, 0.5 + 0.18 * Math.sin(t / 600));
    ctx.stroke();
    ctx.lineWidth = 1.5;
    ctx.strokeStyle = withAlpha('#ffffff', 0.35);
    ctx.stroke();
    ctx.restore();
  }

  // Flood: translucent water creeps over the low grass rim.
  function drawFlood(ctx, geo, pal, weather, t) {
    const f = weather.flood || 0;
    if (f <= 0) return;
    const k = 1 - 0.18 * f;                 // water eats inward as flood rises
    const lvl = LANDH * (0.18 + 0.34 * f);  // water surface elevation on land
    const pts = geo.ground.map(p =>
      project(geo.cx + (p.gx - geo.cx) * k, geo.cy + (p.gy - geo.cy) * k, lvl));
    ctx.save();
    smoothClosedPath(ctx, pts);
    ctx.fillStyle = withAlpha(pal.waterShallow, 0.5 + 0.15 * f);
    ctx.fill();
    // shimmer lines
    ctx.clip();
    ctx.strokeStyle = withAlpha('#ffffff', 0.10);
    ctx.lineWidth = 1;
    for (let y = -120; y < 220; y += 7) {
      ctx.beginPath();
      ctx.moveTo(-400, y + Math.sin((y + t / 40) / 18) * 2);
      ctx.lineTo(400, y + Math.cos((y + t / 40) / 16) * 2);
      ctx.stroke();
    }
    ctx.restore();
  }

  // ---- ground patches (fields / dirt / pond) -------------------------
  // poly given as array of [gx,gy] in ground space at land elevation.
  function patch(ctx, pts, color, opt) {
    opt = opt || {};
    const sp = pts.map(p => project(p[0], p[1], (opt.h == null ? LANDH : opt.h) + 0.4));
    ctx.save();
    if (opt.smooth) smoothClosedPath(ctx, sp);
    else { ctx.beginPath(); ctx.moveTo(sp[0].x, sp[0].y); for (let i = 1; i < sp.length; i++) ctx.lineTo(sp[i].x, sp[i].y); ctx.closePath(); }
    ctx.fillStyle = color; ctx.fill();
    if (opt.stroke) { ctx.strokeStyle = opt.stroke; ctx.lineWidth = opt.lw || 1; ctx.stroke(); }
    ctx.restore();
    return sp;
  }

  global.Island = {
    LANDH, THICK, generate, isLand, drawBase, drawShoreFoam, drawFlood, patch,
  };
})(window);
