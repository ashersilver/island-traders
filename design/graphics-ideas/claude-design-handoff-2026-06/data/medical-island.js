/* ============================================================
   medical-island.js — Healthcare & Research island definition.
   Mandatory: Main Hospital, Medical Clinic.
   ============================================================ */
(function (global) {
  'use strict';
  const S = global.Sprites, Iso = global.Iso;
  const { shade, mix } = Iso;
  const H = global.Island.LANDH;
  const d = (gx, gy, fn) => ({ depth: Iso.depth(gx, gy), gx, gy, fn });

  const MED = {
    id: 'medic',
    role: 'Medical',
    name: 'Healthcare & Research',
    pill: 'Healthcare',
    tagline: 'The best medicine is being here.',

    shape: { seed: 3344, radius: 6.2, wobble: 0.13, lobes: 4, cx: 0, cy: 0 },

    paletteOverride(pal) {
      pal.grass = mix(pal.grass, '#6a9060', 0.14);
      pal.sand  = mix(pal.sand,  '#d8d0c0', 0.10);
      return pal;
    },

    scenery(pal, flags, t) {
      const L = [];
      L.push(d(-3.6, -1.8, (c) => S.tree(c,  -3.6, -1.8, pal, { scale: 1.00, flags })));
      L.push(d(-3.2, -3.0, (c) => S.pine(c,  -3.2, -3.0, pal, { scale: 0.90, flags })));
      L.push(d( 3.7, -1.6, (c) => S.tree(c,   3.7, -1.6, pal, { scale: 0.90, flags })));
      L.push(d(-3.8,  0.8, (c) => S.tree(c,  -3.8,  0.8, pal, { scale: 0.85, flags })));
      L.push(d( 3.8,  1.0, (c) => S.bush(c,   3.8,  1.0, pal, { scale: 1.00, flags })));
      L.push(d(-3.5,  2.6, (c) => S.bush(c,  -3.5,  2.6, pal, { scale: 0.90, flags })));
      L.push(d( 3.5,  2.3, (c) => S.tree(c,   3.5,  2.3, pal, { scale: 0.80, flags })));
      L.push(d(-2.6, -2.6, (c) => S.tree(c,  -2.6, -2.6, pal, { scale: 0.85, flags })));
      L.push(d( 2.6, -2.8, (c) => S.rocks(c,  2.6, -2.8, pal, { scale: 1.30, flags })));
      L.push(d( 2.6, -2.7, (c, tt) => S.lighthouse(c, 2.6, -2.9, pal, {}, tt)));
      L.push(d( 0.3,  3.6, (c) => S.dock(c, 0.3, 3.6, pal, { w: 2.5, l: 1.8 })));
      L.push(d(-0.5,  5.4, (c, tt) => S.fishingBoat(c, -0.5, 5.4, pal, {}, tt)));
      return L;
    },

    fields: [],

    items: [
      {
        id: 'med.hospital', name: 'Main Hospital', cost: 200,
        mandatory: true, group: 'Capital equipment',
        desc: '+50 Patient capacity',
        parts: (pal, flags, t) => [
          d(-0.4, 0.2, (c) => S.hospitalBlock(c, -0.4, 0.2, pal, { flags })),
        ],
      },
      {
        id: 'med.clinic', name: 'Medical Clinic', cost: 80,
        mandatory: true, group: 'Capital equipment',
        desc: '+20 Patient capacity',
        parts: (pal, flags, t) => [
          d(1.8, 0.9, (c) => S.medClinic(c, 1.8, 0.9, pal, { flags })),
        ],
      },
      {
        id: 'med.research_dome', name: 'Research Centre', cost: 120,
        mandatory: false, group: 'Capital equipment',
        desc: '+30 Medical research',
        parts: (pal, flags, t) => [
          d(0.7, -1.5, (c, tt) => S.researchDome(c, 0.7, -1.5, pal, { flags }, tt)),
        ],
      },
      {
        id: 'med.helipad', name: 'Emergency Helipad', cost: 60,
        mandatory: false, group: 'Capital equipment',
        desc: '+20 Emergency response',
        parts: (pal, flags, t) => [
          d(2.9, -0.7, (c, tt) => S.helipad(c, 2.9, -0.7, pal, { flags }, tt)),
        ],
      },
      {
        id: 'med.pharmacy', name: 'Pharmacy & Labs', cost: 90,
        mandatory: false, group: 'Capital equipment',
        desc: '+15 Research capacity',
        parts: (pal, flags, t) => [
          d(-2.3, -0.9, (c) => S.warehouse(c, -2.3, -0.9, pal, { flags })),
        ],
      },
      {
        id: 'med.satellite', name: 'Research Satellite', cost: 45,
        mandatory: false, group: 'Capital equipment',
        desc: '+10 Research · enables global network',
        parts: (pal, flags, t) => [
          d(-1.2, -2.0, (c, tt) => S.satelliteDish(c, -1.2, -2.0, pal, { scale: 1.2 }, tt)),
        ],
      },
      {
        id: 'common.kitchen', name: 'Kitchen', cost: 80,
        mandatory: false, group: 'Capital equipment',
        desc: 'Up to 6 Food/season for the workforce',
        parts: (pal, flags, t) => [
          d(-3.2, 2.8, (c, tt) => S.kitchenCottage(c, -3.2, 2.8, pal, { flags }, tt)),
        ],
      },
    ],
  };

  global.ISLANDS = global.ISLANDS || {};
  global.ISLANDS.medic = MED;
})(window);
