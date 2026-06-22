/* ============================================================
   manufacturing-island.js — Manufacturing & Industry island.
   Mandatory: Main Factory, Assembly Plant.
   ============================================================ */
(function (global) {
  'use strict';
  const S = global.Sprites, Iso = global.Iso;
  const { shade, mix } = Iso;
  const H = global.Island.LANDH;
  const d = (gx, gy, fn) => ({ depth: Iso.depth(gx, gy), gx, gy, fn });

  const MFG = {
    id: 'manufacturer',
    role: 'Manufacturer',
    name: 'Manufacturing & Industry',
    pill: 'Manufacturing',
    tagline: 'Raw materials in. Finished goods out.',

    shape: { seed: 7834, radius: 6.0, wobble: 0.16, lobes: 4, cx: 0, cy: 0 },

    paletteOverride(pal) {
      pal.grass = mix(pal.grass, '#7a7a70', 0.32);
      pal.sand  = mix(pal.sand,  '#b0a898', 0.28);
      return pal;
    },

    scenery(pal, flags, t) {
      const L = [];
      L.push(d(-3.8, -1.8, (c) => S.rocks(c, -3.8, -1.8, pal, { scale: 1.4, flags })));
      L.push(d(-3.4,  0.5, (c) => S.bush(c,  -3.4,  0.5, pal, { scale: 0.85, flags })));
      L.push(d( 3.6, -1.6, (c) => S.rocks(c,  3.6, -1.6, pal, { scale: 1.2, flags })));
      L.push(d( 3.8,  0.9, (c) => S.bush(c,   3.8,  0.9, pal, { scale: 0.80, flags })));
      L.push(d(-3.6,  2.4, (c) => S.bush(c,  -3.6,  2.4, pal, { scale: 0.90, flags })));
      L.push(d( 3.4,  2.1, (c) => S.bush(c,   3.4,  2.1, pal, { scale: 0.85, flags })));
      L.push(d( 2.8, -2.8, (c) => S.rocks(c,  2.8, -2.8, pal, { scale: 1.5, flags })));
      L.push(d( 2.8, -2.7, (c, tt) => S.lighthouse(c, 2.8, -2.95, pal, {}, tt)));
      L.push(d( 0.2,  3.5, (c) => S.dock(c, 0.2, 3.5, pal, { w: 3.0, l: 2.0 })));
      L.push(d(-1.2,  5.5, (c, tt) => S.supplyBoat(c, -1.2, 5.5, pal, {}, tt)));
      return L;
    },

    fields: [],

    items: [
      {
        id: 'mfg.main_factory', name: 'Main Factory', cost: 120,
        mandatory: true, group: 'Capital equipment',
        desc: '+40 Industrial output',
        parts: (pal, flags, t) => [
          d(0.2, 0.2, (c, tt) => S.factory(c, 0.2, 0.2, pal, { flags }, tt)),
        ],
      },
      {
        id: 'mfg.assembly_plant', name: 'Assembly Plant', cost: 80,
        mandatory: true, group: 'Capital equipment',
        desc: '+20 Finished goods capacity',
        parts: (pal, flags, t) => [
          d(2.0, 0.9, (c) => S.assemblyPlant(c, 2.0, 0.9, pal, { flags })),
        ],
      },
      {
        id: 'mfg.smokestacks', name: 'Industrial Smokestacks', cost: 35,
        mandatory: false, group: 'Capital equipment',
        desc: '+10 Output · signals full production',
        parts: (pal, flags, t) => [
          d(-0.9, -0.8, (c, tt) => S.smokestack(c, -0.9, -0.8, pal, {}, tt)),
          d(-0.1, -1.1, (c, tt) => S.smokestack(c, -0.1, -1.1, pal, { scale: 0.88 }, tt)),
        ],
      },
      {
        id: 'mfg.cooling_towers', name: 'Cooling Towers', cost: 50,
        mandatory: false, group: 'Capital equipment',
        desc: '+15 Power efficiency',
        parts: (pal, flags, t) => [
          d(-1.8, 0.5, (c, tt) => S.coolingTower(c, -1.8, 0.5, pal, {}, tt)),
          d(-2.5, 1.4, (c, tt) => S.coolingTower(c, -2.5, 1.4, pal, { scale: 0.85 }, tt)),
        ],
      },
      {
        id: 'mfg.power_plant', name: 'Power Plant', cost: 90,
        mandatory: false, group: 'Capital equipment',
        desc: '+25 Power capacity',
        parts: (pal, flags, t) => [
          d(-2.2, -0.9, (c) => S.warehouse(c, -2.2, -0.9, pal, { flags })),
        ],
      },
      {
        id: 'mfg.materials_depot', name: 'Materials Depot', cost: 45,
        mandatory: false, group: 'Capital equipment',
        desc: '+15 Raw materials storage',
        parts: (pal, flags, t) => [
          d(2.8, -0.4, (c) => S.warehouse(c, 2.8, -0.4, pal, { flags })),
          d(2.5,  0.9, (c) => S.silo(c, 2.5, 0.9, pal, { flags })),
        ],
      },
      {
        id: 'common.kitchen', name: 'Kitchen', cost: 80,
        mandatory: false, group: 'Capital equipment',
        desc: 'Up to 6 Food/season for the workforce',
        parts: (pal, flags, t) => [
          d(-3.0, 2.8, (c, tt) => S.kitchenCottage(c, -3.0, 2.8, pal, { flags }, tt)),
        ],
      },
    ],
  };

  global.ISLANDS = global.ISLANDS || {};
  global.ISLANDS.manufacturer = MFG;
})(window);
