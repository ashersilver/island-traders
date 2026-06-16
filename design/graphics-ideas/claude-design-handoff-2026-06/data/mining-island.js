/* ============================================================
   mining-island.js — Mining & Resources island definition.
   Mandatory: Excavator, Crusher, Oil Rig.
   ============================================================ */
(function (global) {
  'use strict';
  const S = global.Sprites, Iso = global.Iso;
  const { shade, mix, withAlpha, patch } = Iso;
  const H = global.Island.LANDH;
  const d = (gx, gy, fn) => ({ depth: Iso.depth(gx, gy), gx, gy, fn });

  const MINE = {
    id: 'miner',
    role: 'Miner',
    name: 'Mining & Resources',
    tagline: 'Ore, Oil & Metal — the archipelago\'s engine room.',

    // Jagged, dramatic coastline with a prominent rocky headland
    shape: {
      seed: 3317,
      radius: 6.2,
      wobble: 0.24,
      lobes: 6,
      cx: 0,
      cy: 0,
    },

    // Mining-island specific palette overrides (rocky, dusty, sparse grass)
    paletteOverride(pal) {
      pal.grass     = mix(pal.grass, pal.rock, 0.42);     // sparse, dusty
      pal.sand      = mix(pal.sand, '#c4b898', 0.4);      // dusty/gravelly
      pal.soil      = mix(pal.soil, pal.rock, 0.25);
      pal.soilDark  = shade(pal.soilDark, -0.06);
      pal.sky       = mix(pal.sky, '#c4caca', 0.25);
      pal.skyLow    = mix(pal.skyLow, '#d0d4cc', 0.20);
      return pal;
    },

    // ---- always-present scenery & infrastructure ----------------------
    scenery(pal, flags, t) {
      const L = [];
      // Dramatic rocky mountain — dominates north-west
      L.push(d(-1.8, -2.4, (c, tt) => S.mountain(c, -1.8, -2.4, pal, { scale: 1.0, flags, seed: 11 }, tt)));
      // Secondary rock clusters around the island
      L.push(d(1.6, -3.0, (c) => S.rocks(c, 1.6, -3.0, pal, { scale: 1.6, flags })));
      L.push(d(3.2, -1.8, (c) => S.rocks(c, 3.2, -1.8, pal, { scale: 1.3, flags })));
      L.push(d(-3.6, 1.4, (c) => S.rocks(c, -3.6, 1.4, pal, { scale: 1.1, flags })));
      L.push(d(3.6, 1.6, (c) => S.rocks(c, 3.6, 1.6, pal, { scale: 1.0, flags })));
      L.push(d(-3.0, -1.0, (c) => S.rocks(c, -3.0, -1.0, pal, { scale: 0.9, flags })));
      // A few sparse conifers
      L.push(d(0.6, -3.2, (c) => S.pine(c, 0.6, -3.2, pal, { scale: 0.8, flags })));
      L.push(d(-3.8, -0.4, (c) => S.pine(c, -3.8, -0.4, pal, { scale: 0.9, flags })));
      L.push(d(3.8, 0.4, (c) => S.pine(c, 3.8, 0.4, pal, { scale: 0.75, flags })));
      // Mine entrance cut into the mountain base
      L.push(d(-2.0, -0.8, (c) => S.mineEntrance(c, -2.0, -0.8, pal, { flags })));
      // Ore heaps near mine exit
      L.push(d(-0.8, -0.5, (c) => S.oreHeap(c, -0.8, -0.5, pal, { scale: 1.1, seed: 2 })));
      L.push(d(-0.2, -0.2, (c) => S.oreHeap(c, -0.2, -0.2, pal, { scale: 0.8, seed: 5 })));
      // Dump truck on the track from mine
      L.push(d(-1.2, 0.4, (c) => S.dumpTruck(c, -1.2, 0.4, pal, {})));
      // Workers' quarters / site office (small building)
      L.push(d(-3.2, 2.4, (c, tt) => S.farmhouse(c, -3.2, 2.4, pal, { flags }, tt)));
      // Dock + supply boat
      L.push(d(1.0, 4.0, (c) => S.dock(c, 1.0, 4.0, pal, { w: 1.6, l: 2.4 })));
      L.push(d(2.6, 5.2, (c, tt) => S.supplyBoat(c, 2.6, 5.2, pal, {}, tt)));
      return L;
    },

    // ---- no crop fields on mining island -----------------------------
    fields: [],

    // ---- capital catalogue items -------------------------------------
    items: [
      {
        id: 'miner.excavator', name: 'Excavator', cost: 70, mandatory: true, group: 'Capital equipment',
        desc: '+40 Ore capacity',
        parts: (pal, flags, t) => {
          // Big excavator arm near mine entrance
          const L = [];
          L.push(d(-1.4, 1.2, (c, tt) => drawExcavator(c, -1.4, 1.2, pal, flags, tt)));
          return L;
        },
      },
      {
        id: 'miner.crusher', name: 'Crusher', cost: 50, mandatory: true, group: 'Capital equipment',
        desc: '+20 Ore, +20 Metal, −0.2 Oil/Ore',
        parts: (pal, flags, t) => [
          d(0.8, 1.0, (c, tt) => S.crusher(c, 0.8, 1.0, pal, { flags }, tt)),
        ],
      },
      {
        id: 'miner.oil_rig', name: 'Oil Rig', cost: 110, mandatory: true, group: 'Capital equipment',
        desc: '+40 Oil capacity',
        parts: (pal, flags, t) => [
          d(2.4, -0.8, (c, tt) => S.oilDerrick(c, 2.4, -0.8, pal, { scale: 1.0, flags }, tt)),
        ],
      },
      {
        id: 'miner.enhanced_crusher_smelter', name: 'Enhanced Crusher & Smelter', cost: 140, mandatory: false, group: 'Capital equipment',
        desc: '+60 Metal, ×3 productivity, −50% Oil/Metal',
        parts: (pal, flags, t) => [
          d(-0.2, 2.2, (c, tt) => S.smelter(c, -0.2, 2.2, pal, { flags }, tt)),
        ],
      },
      {
        id: 'miner.refinery', name: 'Refinery', cost: 100, mandatory: false, group: 'Capital equipment',
        desc: '+20 Oil, enables RefinerySpecialist',
        parts: (pal, flags, t) => [
          d(3.0, 1.8, (c, tt) => S.refinery(c, 3.0, 1.8, pal, { flags }, tt)),
        ],
      },
      {
        id: 'common.kitchen', name: 'Kitchen', cost: 80, mandatory: false, group: 'Capital equipment',
        desc: 'Up to 6 Food/season for the workforce',
        parts: (pal, flags, t) => [
          d(-3.0, 3.2, (c, tt) => S.kitchenCottage(c, -3.0, 3.2, pal, { flags }, tt)),
        ],
      },
    ],
  };

  // ---- inline excavator sprite (specific to mining) -----------------
  function drawExcavator(ctx, gx, gy, pal, flags, t) {
    const I = Iso;
    const dark = mix(pal.building, '#2a3a42', 0.5);
    const yellow = mix(pal.roofWarm, '#c4a020', 0.55);
    // tracks
    for (const dy of [-0.28, 0.28]) {
      const tl = I.project(gx-0.55, gy+dy, H), tr = I.project(gx+0.55, gy+dy, H);
      const tlT = I.project(gx-0.55, gy+dy, H+5), trT = I.project(gx+0.55, gy+dy, H+5);
      const bl = I.project(gx-0.55, gy+dy+0.12, H), br = I.project(gx+0.55, gy+dy+0.12, H);
      // track body
      ctx.save();
      ctx.beginPath(); ctx.moveTo(tl.x-6,tl.y); ctx.lineTo(tr.x+6,tr.y); ctx.lineTo(tr.x+6,trT.y); ctx.lineTo(tl.x-6,tlT.y); ctx.closePath();
      ctx.fillStyle = dark; ctx.fill();
      ctx.restore();
    }
    // cab body
    isoBox(ctx, gx, gy, 0.9, 0.5, 16, H+5, yellow, { top: shade(yellow,0.08), left: shade(yellow,-0.28), right: shade(yellow,-0.14), edge: shade(yellow,-0.35) });
    // rotating upper house
    isoBox(ctx, gx-0.1, gy, 0.6, 0.44, 10, H+20, shade(yellow,-0.06));
    // cab windows
    const cwin = I.project(gx+0.2, gy+0.2, H+26);
    ctx.save(); ctx.translate(cwin.x,cwin.y); ctx.transform(1,0.5,0,1,0,0);
    ctx.fillStyle=withAlpha('#bfe0e4',0.85); ctx.fillRect(-4,-6,9,8); ctx.restore();
    // boom arm
    const base = I.project(gx+0.1, gy-0.2, H+24);
    const elbow = I.project(gx+0.7, gy-0.5, H+32);
    const tip = I.project(gx+1.3, gy-0.3, H+14);
    ctx.strokeStyle=dark; ctx.lineWidth=5;
    ctx.beginPath(); ctx.moveTo(base.x,base.y); ctx.lineTo(elbow.x,elbow.y); ctx.lineTo(tip.x,tip.y); ctx.stroke();
    ctx.lineWidth=7; ctx.strokeStyle=shade(yellow,-0.15);
    ctx.beginPath(); ctx.moveTo(base.x,base.y); ctx.lineTo(elbow.x,elbow.y); ctx.stroke();
    // bucket
    const bkt = I.project(gx+1.4, gy-0.1, H+8);
    ctx.fillStyle=dark; ctx.beginPath(); ctx.moveTo(bkt.x-8,bkt.y-6); ctx.lineTo(bkt.x+5,bkt.y-6); ctx.lineTo(bkt.x+8,bkt.y+2); ctx.lineTo(bkt.x-5,bkt.y+6); ctx.closePath(); ctx.fill();
    // ore in bucket hint
    const oreC = mix(pal.rockDark,'#7a5830',0.55);
    ctx.fillStyle=oreC; ctx.beginPath(); ctx.arc(bkt.x,bkt.y,3.5,0,6.28); ctx.fill();
  }

  global.ISLANDS = global.ISLANDS || {};
  global.ISLANDS.miner = MINE;
})(window);
