/* ============================================================
   iso.js — Isometric projection, drawing primitives, utilities
   Island Traders · dynamic island graphics
   ============================================================ */
(function (global) {
  'use strict';

  // ---- Isometric config (2:1 dimetric) --------------------------------
  // One ground unit projects to a diamond TILE wide, TILE/2 tall.
  const ISO = {
    TILE: 30,        // half-width of a ground unit in px
    get HALF() { return this.TILE; },
    get QUART() { return this.TILE / 2; },
  };

  // Project a ground point (gx, gy) at elevation h(px) to screen px.
  // Returns {x, y}. Camera origin + scale applied by caller's transform.
  function project(gx, gy, h) {
    h = h || 0;
    return {
      x: (gx - gy) * ISO.TILE,
      y: (gx + gy) * ISO.QUART - h,
    };
  }

  // Depth key for painter's algorithm (larger = nearer/front).
  function depth(gx, gy, h) {
    return (gx + gy) * 1000 + (h || 0) * 0.5;
  }

  // ---- Seeded RNG (mulberry32) ----------------------------------------
  function makeRNG(seed) {
    let a = seed >>> 0;
    return function () {
      a |= 0; a = (a + 0x6D2B79F5) | 0;
      let t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  // Smooth periodic 1D noise over angle (for organic coastlines).
  function makeAngularNoise(seed, octaves) {
    const rng = makeRNG(seed);
    const harmonics = [];
    octaves = octaves || 4;
    for (let i = 1; i <= octaves; i++) {
      harmonics.push({
        freq: i,
        amp: 1 / i,
        phase: rng() * Math.PI * 2,
      });
    }
    const norm = harmonics.reduce((s, h) => s + h.amp, 0);
    return function (theta) {
      let v = 0;
      for (const h of harmonics) v += Math.sin(theta * h.freq + h.phase) * h.amp;
      return v / norm; // -1..1
    };
  }

  // ---- Color utilities -------------------------------------------------
  function hexToRgb(hex) {
    hex = hex.replace('#', '');
    if (hex.length === 3) hex = hex.split('').map(c => c + c).join('');
    const n = parseInt(hex, 16);
    return { r: (n >> 16) & 255, g: (n >> 8) & 255, b: n & 255 };
  }
  function rgbToHex(r, g, b) {
    const c = v => Math.max(0, Math.min(255, Math.round(v))).toString(16).padStart(2, '0');
    return '#' + c(r) + c(g) + c(b);
  }
  function shade(hex, amt) {
    // amt -1..1 ; negative darkens, positive lightens
    const { r, g, b } = hexToRgb(hex);
    if (amt >= 0) return rgbToHex(r + (255 - r) * amt, g + (255 - g) * amt, b + (255 - b) * amt);
    return rgbToHex(r * (1 + amt), g * (1 + amt), b * (1 + amt));
  }
  function mix(a, b, t) {
    const ca = hexToRgb(a), cb = hexToRgb(b);
    return rgbToHex(ca.r + (cb.r - ca.r) * t, ca.g + (cb.g - ca.g) * t, ca.b + (cb.b - ca.b) * t);
  }
  function withAlpha(hex, a) {
    const { r, g, b } = hexToRgb(hex);
    return `rgba(${r},${g},${b},${a})`;
  }
  // Desaturate toward grey by amount 0..1
  function desat(hex, amt) {
    const { r, g, b } = hexToRgb(hex);
    const l = 0.3 * r + 0.59 * g + 0.11 * b;
    return rgbToHex(r + (l - r) * amt, g + (l - g) * amt, b + (l - b) * amt);
  }

  // ---- Primitive: filled polygon from screen points -------------------
  function poly(ctx, pts, fill, stroke, lw) {
    ctx.beginPath();
    ctx.moveTo(pts[0].x, pts[0].y);
    for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i].x, pts[i].y);
    ctx.closePath();
    if (fill) { ctx.fillStyle = fill; ctx.fill(); }
    if (stroke) { ctx.strokeStyle = stroke; ctx.lineWidth = lw || 1; ctx.lineJoin = 'round'; ctx.stroke(); }
  }

  // ---- Primitive: smooth closed curve through points (Catmull-Rom) ----
  function smoothClosedPath(ctx, pts) {
    const n = pts.length;
    ctx.beginPath();
    ctx.moveTo((pts[n - 1].x + pts[0].x) / 2, (pts[n - 1].y + pts[0].y) / 2);
    for (let i = 0; i < n; i++) {
      const p0 = pts[i];
      const p1 = pts[(i + 1) % n];
      const mx = (p0.x + p1.x) / 2, my = (p0.y + p1.y) / 2;
      ctx.quadraticCurveTo(p0.x, p0.y, mx, my);
    }
    ctx.closePath();
  }

  // ---- Primitive: isometric box (cuboid) ------------------------------
  // Origin at ground centre (gx, gy). Size in ground units (sx, sy) and px height hz.
  // Base sits at elevation baseH (px). Faces shaded from a top color.
  function isoBox(ctx, gx, gy, sx, sy, hz, baseH, topColor, opt) {
    opt = opt || {};
    const hx = sx / 2, hy = sy / 2;
    const bH = baseH || 0;
    // four ground corners
    const A = project(gx - hx, gy - hy, bH); // back   (top of diamond)
    const B = project(gx + hx, gy - hy, bH); // right
    const C = project(gx + hx, gy + hy, bH); // front  (bottom)
    const D = project(gx - hx, gy + hy, bH); // left
    const At = project(gx - hx, gy - hy, bH + hz);
    const Bt = project(gx + hx, gy - hy, bH + hz);
    const Ct = project(gx + hx, gy + hy, bH + hz);
    const Dt = project(gx - hx, gy + hy, bH + hz);

    const left = opt.left || shade(topColor, -0.28);
    const right = opt.right || shade(topColor, -0.14);
    const top = opt.top || topColor;
    const edge = opt.edge || null;
    const lw = opt.lw || 1;

    // left face (D-C-Ct-Dt)
    poly(ctx, [D, C, Ct, Dt], left, edge, lw);
    // right face (C-B-Bt-Ct)
    poly(ctx, [C, B, Bt, Ct], right, edge, lw);
    // top (At-Bt-Ct-Dt)
    poly(ctx, [At, Bt, Ct, Dt], top, edge, lw);
    return { At, Bt, Ct, Dt, A, B, C, D };
  }

  // ---- Primitive: isometric pyramid / prism roof ----------------------
  function isoRoof(ctx, gx, gy, sx, sy, hz, baseH, color, opt) {
    opt = opt || {};
    const hx = sx / 2, hy = sy / 2;
    const bH = baseH || 0;
    const At = project(gx - hx, gy - hy, bH);
    const Bt = project(gx + hx, gy - hy, bH);
    const Ct = project(gx + hx, gy + hy, bH);
    const Dt = project(gx - hx, gy + hy, bH);
    const apex = project(gx, gy, bH + hz);
    const left = opt.left || shade(color, -0.22);
    const right = opt.right || shade(color, -0.10);
    const back = opt.back || shade(color, -0.30);
    const edge = opt.edge || null;
    poly(ctx, [Dt, At, apex], back, edge, 1);   // back-left
    poly(ctx, [At, Bt, apex], shade(color, 0.02), edge, 1); // back-right (lit)
    poly(ctx, [Dt, Ct, apex], left, edge, 1);   // front-left
    poly(ctx, [Ct, Bt, apex], right, edge, 1);  // front-right
    return apex;
  }

  // ---- Primitive: gable roof (ridge along x) --------------------------
  function gableRoof(ctx, gx, gy, sx, sy, hz, baseH, color, opt) {
    opt = opt || {};
    const hx = sx / 2, hy = sy / 2;
    const bH = baseH || 0;
    const Dt = project(gx - hx, gy + hy, bH); // front-left eave
    const Ct = project(gx + hx, gy + hy, bH); // front-right eave
    const At = project(gx - hx, gy - hy, bH); // back-left eave
    const Bt = project(gx + hx, gy - hy, bH); // back-right eave
    const ridgeF = project(gx, gy + hy, bH + hz);
    const ridgeB = project(gx, gy - hy, bH + hz);
    const left = opt.left || shade(color, -0.06);
    const right = opt.right || shade(color, -0.24);
    const edge = opt.edge || null;
    // left slope (front-left to back-left over ridge)
    poly(ctx, [Dt, At, ridgeB, ridgeF], left, edge, 1);
    // right slope
    poly(ctx, [Ct, Bt, ridgeB, ridgeF], right, edge, 1);
    // gable triangles (front + back)
    poly(ctx, [Dt, Ct, ridgeF], shade(color, -0.34), edge, 1);
    return { ridgeF, ridgeB };
  }

  // ---- Primitive: vertical cylinder (silo/tank/chimney) ---------------
  function isoCylinder(ctx, gx, gy, rad, hz, baseH, color, opt) {
    opt = opt || {};
    const bH = baseH || 0;
    const c0 = project(gx, gy, bH);
    const ct = project(gx, gy, bH + hz);
    const rx = rad * ISO.TILE;     // screen radius x
    const ry = rad * ISO.QUART;    // screen radius y (iso squash)
    // body
    ctx.beginPath();
    ctx.moveTo(c0.x - rx, c0.y);
    ctx.lineTo(c0.x - rx, ct.y);
    ctx.ellipse(ct.x, ct.y, rx, ry, 0, Math.PI, 0, true);
    ctx.lineTo(c0.x + rx, c0.y);
    ctx.ellipse(c0.x, c0.y, rx, ry, 0, 0, Math.PI, false);
    ctx.closePath();
    // vertical light gradient on body
    const g = ctx.createLinearGradient(c0.x - rx, 0, c0.x + rx, 0);
    g.addColorStop(0, shade(color, -0.26));
    g.addColorStop(0.5, color);
    g.addColorStop(1, shade(color, -0.12));
    ctx.fillStyle = g; ctx.fill();
    if (opt.edge) { ctx.strokeStyle = opt.edge; ctx.lineWidth = 1; ctx.stroke(); }
    // top cap
    ctx.beginPath();
    ctx.ellipse(ct.x, ct.y, rx, ry, 0, 0, Math.PI * 2);
    ctx.fillStyle = opt.top || shade(color, 0.18); ctx.fill();
    if (opt.edge) ctx.stroke();
    return { c0, ct, rx, ry };
  }

  // ---- Soft contact shadow (ellipse) ----------------------------------
  function blob(ctx, gx, gy, rad, baseH, alpha) {
    const c = project(gx, gy, baseH || 0);
    const rx = rad * ISO.TILE, ry = rad * ISO.QUART;
    ctx.save();
    ctx.beginPath();
    ctx.ellipse(c.x, c.y, rx, ry, 0, 0, Math.PI * 2);
    ctx.fillStyle = `rgba(12,20,28,${alpha == null ? 0.18 : alpha})`;
    ctx.filter = 'blur(2px)';
    ctx.fill();
    ctx.restore();
  }

  global.Iso = {
    ISO, project, depth, makeRNG, makeAngularNoise,
    hexToRgb, rgbToHex, shade, mix, withAlpha, desat,
    poly, smoothClosedPath, isoBox, isoRoof, gableRoof, isoCylinder, blob,
  };
})(window);
