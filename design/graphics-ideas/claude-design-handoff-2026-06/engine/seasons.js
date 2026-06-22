/* ============================================================
   seasons.js — Season palettes, weather states, atmosphere
   ============================================================ */
(function (global) {
  'use strict';
  const I = global.Iso;
  const { shade, mix, desat, withAlpha } = I;

  // Base (summer-day) palette — keyed to the diorama renders:
  // dark-teal water, warm sand, warm green, earthy soil.
  const BASE = {
    waterDeep: '#1d4856',
    waterShallow: '#2f7d92',
    foam: '#cfe9ea',
    sand: '#d9c298',
    sandDark: '#b59668',
    grass: '#6f8f45',
    soil: '#7c5634',
    soilDark: '#46301d',
    rock: '#8d877b',
    rockDark: '#5f5a50',
    leaf: '#5f7f3a',
    leafDark: '#3f5a26',
    trunk: '#6b4a2e',
    crop: '#caa83f',          // ripe grain
    cropYoung: '#7faa4c',
    cropField: '#c8a85a',
    building: '#2c5560',      // dark-teal structures
    buildingWarm: '#caa06a',
    roof: '#244651',
    roofWarm: '#9a5034',
    woodDock: '#b98f56',
    woodDockDark: '#8a6638',
    window: '#f4c761',
    ambient: 'rgba(255,225,170,0)', // light wash (color, applied at alpha)
    ambientA: 0.0,
    sky: '#bcd3d8',           // backdrop top
    skyLow: '#dfe7e0',
  };

  // Season definitions return a palette + descriptive flags.
  const SEASONS = {
    spring: {
      label: 'Spring',
      apply(p) {
        p.grass = '#7fa84e';
        p.leaf = '#6f9b3e'; p.leafDark = '#4f7a2a';
        p.crop = '#9fc25a'; p.cropField = '#9bbf57'; // young planting
        p.waterDeep = '#1f5160'; p.waterShallow = '#3a93a6';
        p.sky = '#cfe0e2'; p.skyLow = '#e9efe6';
        p.ambient = 'rgba(255,240,210,1)'; p.ambientA = 0.05;
        return { snow: 0, blossom: 1, cropStage: 0.35, fishRun: 0.8, foliage: 1 };
      },
    },
    summer: {
      label: 'Summer',
      apply(p) {
        // base is summer
        p.ambient = 'rgba(255,214,150,1)'; p.ambientA = 0.10;
        return { snow: 0, blossom: 0, cropStage: 0.7, fishRun: 1, foliage: 1 };
      },
    },
    autumn: {
      label: 'Autumn',
      apply(p) {
        p.grass = '#9a9a46';
        p.leaf = '#b5742a'; p.leafDark = '#8a4f22';
        p.crop = '#d9a93c'; p.cropField = '#d2a23f';
        p.waterDeep = '#23454f'; p.waterShallow = '#357585';
        p.sky = '#d9cdb6'; p.skyLow = '#ece2cc';
        p.sand = '#d2b889';
        p.ambient = 'rgba(255,190,120,1)'; p.ambientA = 0.14;
        return { snow: 0, blossom: 0, cropStage: 1, fishRun: 0.5, foliage: 0.7, harvest: 1 };
      },
    },
    winter: {
      label: 'Winter',
      apply(p) {
        p.grass = mix('#6f8f45', '#eef3f4', 0.78);
        p.sand = mix(p.sand, '#eef2f3', 0.5);
        p.leaf = '#7c8a6a'; p.leafDark = '#5b6a4d';
        p.crop = '#cdb98e'; p.cropField = mix('#c8a85a', '#eef3f4', 0.6);
        p.waterDeep = '#274854'; p.waterShallow = '#4a7e8c';
        p.foam = '#eef6f7';
        p.soil = mix(p.soil, '#cfd6d6', 0.25);
        p.sky = '#cdd6d8'; p.skyLow = '#e7ecee';
        p.ambient = 'rgba(200,225,255,1)'; p.ambientA = 0.12;
        return { snow: 1, blossom: 0, cropStage: 0, fishRun: 0.3, foliage: 0.15, bare: 1 };
      },
    },
  };

  // Weather overlays mutate palette + flags further.
  const WEATHER = {
    normal: { label: 'Normal', apply(p, f) { return { flood: 0, drought: 0 }; } },
    drought: {
      label: 'Drought',
      apply(p, f) {
        p.grass = desat(mix(p.grass, '#b89a4e', 0.55), 0.25);
        p.crop = mix(p.crop, '#b98f3a', 0.4);
        p.cropField = desat(mix(p.cropField, '#bfa055', 0.5), 0.2);
        p.leaf = desat(mix(p.leaf, '#9a8746', 0.4), 0.2);
        p.sand = mix(p.sand, '#d8c089', 0.5);
        p.waterDeep = shade(p.waterDeep, -0.10);
        p.waterShallow = mix(p.waterShallow, '#7d8a6a', 0.3);
        p.sky = mix(p.sky, '#e6d8b4', 0.5); p.skyLow = mix(p.skyLow, '#ecdcb8', 0.5);
        p.ambient = 'rgba(255,180,90,1)'; p.ambientA = Math.max(p.ambientA, 0.16);
        f.fishRun = (f.fishRun || 1) * 0.4;
        return { flood: 0, drought: 1 };
      },
    },
    flood: {
      label: 'Flood',
      apply(p, f) {
        p.waterShallow = mix(p.waterShallow, '#5b6f6a', 0.35);
        p.waterDeep = shade(p.waterDeep, -0.06);
        p.grass = shade(p.grass, -0.10);
        p.sky = mix(p.sky, '#9aa6a8', 0.55); p.skyLow = mix(p.skyLow, '#aeb6b4', 0.5);
        p.ambient = 'rgba(120,140,160,1)'; p.ambientA = Math.max(p.ambientA, 0.14);
        return { flood: 1, drought: 0, rain: 0.8 };
      },
    },
  };

  // Resolve season + weather into a palette and a flags object.
  function resolve(seasonKey, weatherKey) {
    const p = Object.assign({}, BASE);
    const sFlags = (SEASONS[seasonKey] || SEASONS.summer).apply(p);
    const wFlags = (WEATHER[weatherKey] || WEATHER.normal).apply(p, sFlags);
    return { pal: p, flags: Object.assign({}, sFlags, wFlags) };
  }

  // ---------------- Particle systems ----------------------------------
  function makeParticles() {
    let snow = [], rain = [], leaves = [], smoke = [];
    const rng = Math.random;
    function ensure(arr, n, mk) { while (arr.length < n) arr.push(mk()); if (arr.length > n) arr.length = n; }

    return {
      update(flags, t, W, H, dt) {
        // snow
        ensure(snow, flags.snow ? 130 : 0, () => ({ x: rng() * W, y: rng() * H, r: 1 + rng() * 2.2, s: 0.3 + rng() * 0.7, sway: rng() * 6 }));
        for (const f of snow) { f.y += f.s * dt * 0.06; f.x += Math.sin((t / 700) + f.sway) * 0.3; if (f.y > H) { f.y = -5; f.x = rng() * W; } }
        // rain
        const rainN = flags.rain ? Math.round(220 * flags.rain) : 0;
        ensure(rain, rainN, () => ({ x: rng() * W, y: rng() * H, l: 8 + rng() * 10, s: 6 + rng() * 5 }));
        for (const d of rain) { d.y += d.s * dt * 0.12; d.x += d.s * dt * 0.03; if (d.y > H) { d.y = -10; d.x = rng() * W; } }
        // falling leaves (autumn)
        const leafN = flags.harvest && !flags.drought ? 26 : 0;
        ensure(leaves, leafN, () => ({ x: rng() * W, y: rng() * H, r: 2 + rng() * 2, s: 0.4 + rng() * 0.5, rot: rng() * 6, vr: (rng() - 0.5) * 0.1, sway: rng() * 6 }));
        for (const l of leaves) { l.y += l.s * dt * 0.05; l.x += Math.sin(t / 600 + l.sway) * 0.5; l.rot += l.vr; if (l.y > H) { l.y = -8; l.x = rng() * W; } }
      },
      drawBack(ctx, flags, t, W, H) {
        // rain behind foreground? keep rain in front. nothing here.
      },
      drawFront(ctx, flags, pal, t, W, H) {
        if (rain.length) {
          ctx.save(); ctx.strokeStyle = 'rgba(200,220,228,0.45)'; ctx.lineWidth = 1;
          for (const d of rain) { ctx.beginPath(); ctx.moveTo(d.x, d.y); ctx.lineTo(d.x - d.l * 0.3, d.y + d.l); ctx.stroke(); }
          ctx.restore();
        }
        if (leaves.length) {
          ctx.save();
          for (const l of leaves) {
            ctx.save(); ctx.translate(l.x, l.y); ctx.rotate(l.rot);
            ctx.fillStyle = withAlpha(pal.leaf, 0.9);
            ctx.beginPath(); ctx.ellipse(0, 0, l.r * 1.6, l.r, 0, 0, Math.PI * 2); ctx.fill();
            ctx.restore();
          }
          ctx.restore();
        }
        if (snow.length) {
          ctx.save(); ctx.fillStyle = 'rgba(255,255,255,0.9)';
          for (const f of snow) { ctx.beginPath(); ctx.arc(f.x, f.y, f.r, 0, Math.PI * 2); ctx.fill(); }
          ctx.restore();
        }
        // drought heat haze: faint warm vignette flicker
        if (flags.drought) {
          ctx.save();
          const a = 0.05 + 0.015 * Math.sin(t / 300);
          ctx.fillStyle = `rgba(255,170,80,${a})`;
          ctx.fillRect(0, 0, W, H);
          ctx.restore();
        }
      },
    };
  }

  global.Seasons = { BASE, SEASONS, WEATHER, resolve, makeParticles };
})(window);
