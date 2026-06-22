/* ============================================================
   farm-island.js — Agriculture, Fisheries & Foods island.
   Maps the real capital catalogue + brief land-use items to
   positions, and assembles a depth-sorted render list.
   ============================================================ */
(function (global) {
  'use strict';
  const S = global.Sprites, C = global.Crops, Iso = global.Iso;
  const d = (gx, gy, fn) => ({ depth: Iso.depth(gx, gy), gx, gy, fn });

  const FARM = {
    id: 'farmer',
    role: 'Farmer',
    name: 'Agriculture, Fisheries & Foods',
    tagline: 'Feeds the archipelago — Grain, Produce & Fish.',
    shape: { radius: 6.4, wobble: 0.18, lobes: 5, seed: 1207, cx: 0, cy: 0 },

    // ---- always-present natural scenery & starting structures --------
    scenery(pal, flags, t) {
      const L = [];
      // rocky hill cluster (back)
      L.push(d(-2.0, -2.8, (c) => S.rocks(c, -2.0, -2.8, pal, { scale: 1.5, flags })));
      L.push(d(-2.7, -2.3, (c) => S.rocks(c, -2.7, -2.3, pal, { scale: 1.1, flags })));
      L.push(d(-1.3, -3.1, (c) => S.rocks(c, -1.3, -3.1, pal, { scale: 1.0, flags })));
      // conifers on the hill + scattered trees
      L.push(d(-3.3, -2.9, (c) => S.pine(c, -3.3, -2.9, pal, { scale: 1.1, flags })));
      L.push(d(-3.7, -2.1, (c) => S.pine(c, -3.7, -2.1, pal, { scale: 0.95, flags })));
      L.push(d(-1.9, -3.7, (c) => S.tree(c, -1.9, -3.7, pal, { scale: 0.9, flags, blossom: true })));
      L.push(d(0.2, -3.4, (c) => S.tree(c, 0.2, -3.4, pal, { scale: 0.85, flags, blossom: true })));
      L.push(d(3.6, 2.4, (c) => S.tree(c, 3.6, 2.4, pal, { scale: 0.9, flags, blossom: true })));
      L.push(d(-3.9, 0.6, (c) => S.tree(c, -3.9, 0.6, pal, { scale: 0.85, flags })));
      L.push(d(4.1, 1.0, (c) => S.bush(c, 4.1, 1.0, pal, { scale: 1.1, flags })));
      L.push(d(-3.6, 2.6, (c) => S.bush(c, -3.6, 2.6, pal, { scale: 1.0, flags })));
      // lighthouse on a rock (back-right headland)
      L.push(d(2.6, -2.9, (c) => S.rocks(c, 2.6, -2.9, pal, { scale: 1.6, flags })));
      L.push(d(2.6, -2.75, (c, tt) => S.lighthouse(c, 2.6, -2.95, pal, {}, tt)));
      // windmill (starting farm infrastructure)
      L.push(d(-3.4, -0.7, (c, tt) => S.windmill(c, -3.4, -0.7, pal, {}, tt)));
      // farmhouse (starting)
      L.push(d(-2.7, 0.7, (c, tt) => S.farmhouse(c, -2.7, 0.7, pal, { flags }, tt)));
      // pickup near yard
      L.push(d(-1.2, 1.7, (c) => S.pickup(c, -1.2, 1.7, pal, {})));
      // market stall
      L.push(d(0.5, 2.8, (c) => S.stall(c, 0.5, 2.8, pal, {})));
      // dock + fish pens (starting waterfront)
      L.push(d(0.9, 3.9, (c) => S.dock(c, 0.9, 3.9, pal, { w: 1.4, l: 2.0 })));
      L.push(d(2.2, 4.4, (c, tt) => S.fishPen(c, 2.2, 4.4, pal, {}, tt)));
      L.push(d(3.1, 5.0, (c, tt) => S.fishPen(c, 3.1, 5.0, pal, {}, tt)));
      return L;
    },

    // ---- productive land (toggleable) --------------------------------
    fields: [
      { id: 'land.grain', name: 'Grain field', group: 'Land & livestock', on: true,
        field: { gx: 2.4, gy: -0.3, w: 2.4, h: 2.1, kind: 'grain', seed: 3 } },
      { id: 'land.corn', name: 'Cornfield', group: 'Land & livestock', on: true,
        field: { gx: 0.5, gy: -0.9, w: 2.0, h: 1.7, kind: 'corn', seed: 5 } },
      { id: 'land.veg', name: 'Vegetable beds', group: 'Land & livestock', on: true,
        field: { gx: -0.9, gy: 0.1, w: 1.6, h: 1.4, kind: 'veg', seed: 8 } },
      { id: 'land.pasture', name: 'Cattle pasture', group: 'Land & livestock', on: false,
        field: { gx: 3.2, gy: 1.8, w: 2.1, h: 1.7, kind: 'pasture', seed: 2 },
        // cattle only appear when both barn is built AND pasture is active
        parts: (pal, flags, t) => [d(3.2, 1.8, (c) => S.cattle(c, 3.2, 1.8, pal, { n: 5, seed: 4 }))] },
    ],

    // ---- catalogue capital items + land/livestock objects ------------
    items: [
      { id: 'farmer.tractor', name: 'Tractor', cost: 60, mandatory: true, group: 'Capital equipment',
        desc: '+10 Grain, +6 Produce capacity',
        // sits inside the grain field
        parts: (pal, flags, t) => [d(2.6, 0.4, (c) => S.tractor(c, 2.6, 0.4, pal, {}))] },
      { id: 'farmer.fishing_boat', name: 'Fishing Boat', cost: 50, mandatory: true, group: 'Capital equipment',
        desc: '+4 Fish capacity', water: true,
        parts: (pal, flags, t) => [d(0.3, 5.6, (c, tt) => S.fishingBoat(c, 0.3, 5.6, pal, {}, tt))] },
      { id: 'farmer.harvester', name: 'Combine Harvester', cost: 90, mandatory: false, group: 'Capital equipment',
        desc: '+6 Grain, +4 Produce, −1 Technician',
        // parked at the edge of the corn field
        parts: (pal, flags, t) => [d(0.4, 0.2, (c) => S.combine(c, 0.4, 0.2, pal, {}))] },
      { id: 'farmer.livestock_barn', name: 'Livestock Barn', cost: 70, mandatory: false, group: 'Capital equipment',
        desc: '+4 Meat capacity · cattle graze in pasture',
        // barn on the west side; cattle appear in/near the pasture field
        parts: (pal, flags, t) => [
          d(-3.1, 1.9, (c, tt) => S.barn(c, -3.1, 1.9, pal, { flags })),
        ] },
      { id: 'farmer.industrial_kitchen', name: 'Industrial Kitchen', cost: 75, mandatory: false, group: 'Capital equipment',
        desc: '+6 packaged Food capacity',
        parts: (pal, flags, t) => [d(-0.7, 2.8, (c) => S.packhouse(c, -0.7, 2.8, pal, { flags }))] },
      { id: 'farmer.storage_building', name: 'Storage Building', cost: 40, mandatory: false, group: 'Capital equipment',
        desc: '+10 inventory cap',
        // warehouse on the north-east flat
        parts: (pal, flags, t) => [d(1.8, -2.2, (c) => S.warehouse(c, 1.8, -2.2, pal, { flags }))] },
      { id: 'common.kitchen', name: 'Kitchen', cost: 80, mandatory: false, group: 'Capital equipment',
        desc: 'Converts ingredients into up to 6 Food/season',
        // standalone cottage, east of the market stall
        parts: (pal, flags, t) => [d(2.3, 2.5, (c, tt) => S.kitchenCottage(c, 2.3, 2.5, pal, { flags }, tt))] },
      // orchard as a land-use object (grid of fruit trees)
      { id: 'land.orchard', name: 'Orchard', cost: null, mandatory: false, group: 'Land & livestock',
        desc: 'Fruit trees — improves Produce',
        parts: (pal, flags, t) => {
          const out = [];
          for (let i = 0; i < 3; i++) for (let j = 0; j < 2; j++) {
            const gx = 3.0 + i * 0.7, gy = -1.9 + j * 0.7;
            out.push(d(gx, gy, (c) => S.tree(c, gx, gy, pal, { scale: 0.62, flags, blossom: true })));
          }
          return out;
        } },
    ],
  };

  global.ISLANDS = global.ISLANDS || {};
  global.ISLANDS.farmer = FARM;
})(window);
