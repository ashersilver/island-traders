/* ============================================================
   banking-island.js — Banking & Insurance island definition.
   Mandatory: Bank of the Island, Insurance House.
   ============================================================ */
(function (global) {
  'use strict';
  const S = global.Sprites, Iso = global.Iso;
  const { shade, mix } = Iso;
  const H = global.Island.LANDH;
  const d = (gx, gy, fn) => ({ depth: Iso.depth(gx, gy), gx, gy, fn });

  const BANK = {
    id: 'banker',
    role: 'Banker',
    name: 'Banking & Insurance',
    pill: 'Finance',
    tagline: 'Capital at work — quietly.',

    shape: { seed: 2277, radius: 5.8, wobble: 0.14, lobes: 4, cx: 0, cy: 0 },

    paletteOverride(pal) {
      pal.grass    = mix(pal.grass,    '#8a8870', 0.22);
      pal.sand     = mix(pal.sand,     '#d0c8a8', 0.20);
      pal.soilDark = mix(pal.soilDark, '#5a5040', 0.18);
      return pal;
    },

    scenery(pal, flags, t) {
      const L = [];
      L.push(d(-3.6, -2.0, (c) => S.tree(c,  -3.6, -2.0, pal, { scale: 0.90, flags })));
      L.push(d( 3.5, -1.8, (c) => S.tree(c,   3.5, -1.8, pal, { scale: 0.85, flags })));
      L.push(d(-3.7,  0.9, (c) => S.bush(c,  -3.7,  0.9, pal, { scale: 1.00, flags })));
      L.push(d( 3.7,  0.7, (c) => S.tree(c,   3.7,  0.7, pal, { scale: 0.80, flags })));
      L.push(d(-3.5,  2.8, (c) => S.bush(c,  -3.5,  2.8, pal, { scale: 0.90, flags })));
      L.push(d( 3.4,  2.4, (c) => S.bush(c,   3.4,  2.4, pal, { scale: 0.85, flags })));
      L.push(d(-2.8, -2.4, (c) => S.tree(c,  -2.8, -2.4, pal, { scale: 0.80, flags })));
      L.push(d( 2.8, -2.8, (c) => S.rocks(c,  2.8, -2.8, pal, { scale: 1.40, flags })));
      L.push(d( 2.8, -2.7, (c, tt) => S.lighthouse(c, 2.8, -2.9, pal, {}, tt)));
      L.push(d( 0.2,  3.5, (c) => S.dock(c, 0.2, 3.5, pal, { w: 2.5, l: 1.8 })));
      L.push(d(-0.8,  5.3, (c, tt) => S.fishingBoat(c, -0.8, 5.3, pal, {}, tt)));
      return L;
    },

    fields: [],

    items: [
      {
        id: 'bank.bank_building', name: 'Bank of the Island', cost: 150,
        mandatory: true, group: 'Capital equipment',
        desc: '+50 Capital capacity',
        parts: (pal, flags, t) => [
          d(-1.6, 0.0, (c) => S.bankBuilding(c, -1.6, 0.0, pal, { flags })),
        ],
      },
      {
        id: 'bank.insurance_office', name: 'Insurance House', cost: 90,
        mandatory: true, group: 'Capital equipment',
        desc: '+30 Risk coverage',
        parts: (pal, flags, t) => [
          d(1.5, -0.5, (c) => S.officeTower(c, 1.5, -0.5, pal, { flags })),
        ],
      },
      {
        id: 'bank.ornamental_pond', name: 'The Reflecting Pool', cost: 30,
        mandatory: false, group: 'Capital equipment',
        desc: 'Prestige · +5 Capital',
        parts: (pal, flags, t) => [
          d(-0.2, 1.1, (c, tt) => S.ornamentalPond(c, -0.2, 1.1, pal, { size: 0.95 }, tt)),
        ],
      },
      {
        id: 'bank.investment_tower', name: 'Investment Tower', cost: 110,
        mandatory: false, group: 'Capital equipment',
        desc: '+20 Capital · +20 Loans',
        parts: (pal, flags, t) => [
          d(2.3, 0.9, (c) => S.officeTower(c, 2.3, 0.9, pal, { flags })),
        ],
      },
      {
        id: 'bank.tax_advisory', name: 'Tax Advisory Centre', cost: 65,
        mandatory: false, group: 'Capital equipment',
        desc: '+15 Revenue efficiency · +10 Loans',
        parts: (pal, flags, t) => [
          d(-2.6, -0.8, (c) => S.warehouse(c, -2.6, -0.8, pal, { flags })),
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
  global.ISLANDS.banker = BANK;
})(window);
