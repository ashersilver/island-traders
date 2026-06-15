/* ============================================================
   transport-island.js — Transport & Logistics island definition.
   Mandatory: Container Terminal, Cargo Crane.
   ============================================================ */
(function (global) {
  'use strict';
  const S = global.Sprites, Iso = global.Iso;
  const { shade, mix, withAlpha } = Iso;
  const H = global.Island.LANDH;
  const d = (gx, gy, fn) => ({ depth: Iso.depth(gx, gy), gx, gy, fn });

  const TRANSPORT = {
    id: 'transporter',
    role: 'Transporter',
    name: 'Transport & Logistics',
    tagline: 'Moves everything that matters — Sea, Land & Air.',

    // Broad, gently indented coastline — harbour-friendly
    shape: {
      seed: 5519,
      radius: 6.1,
      wobble: 0.15,
      lobes: 4,
      cx: 0,
      cy: 0,
    },

    // Palette: concrete-grey, less greenery, more industrial
    paletteOverride(pal) {
      pal.grass    = mix(pal.grass,   '#8a9080', 0.32);
      pal.sand     = mix(pal.sand,    '#c8c0a8', 0.28);
      pal.soil     = mix(pal.soil,    '#8a8078', 0.22);
      pal.soilDark = shade(pal.soilDark, -0.04);
      return pal;
    },

    // ---- always-present scenery & infrastructure ----------------------
    scenery(pal, flags, t) {
      const L = [];

      // Natural edges — rocks & trees give the port a living frame
      L.push(d(-3.7, -1.6, (c) => S.rocks(c, -3.7, -1.6, pal, { scale: 1.3, flags })));
      L.push(d(-3.2, -2.7, (c) => S.pine(c,  -3.2, -2.7, pal, { scale: 1.0, flags })));
      L.push(d(-3.9,  0.5, (c) => S.tree(c,  -3.9,  0.5, pal, { scale: 0.85, flags })));
      L.push(d( 3.7, -2.0, (c) => S.rocks(c,  3.7, -2.0, pal, { scale: 1.2, flags })));
      L.push(d( 3.8,  0.8, (c) => S.bush(c,   3.8,  0.8, pal, { scale: 1.0, flags })));
      L.push(d(-3.5,  2.3, (c) => S.bush(c,  -3.5,  2.3, pal, { scale: 0.9, flags })));
      L.push(d( 3.4,  2.0, (c) => S.bush(c,   3.4,  2.0, pal, { scale: 0.85, flags })));

      // Lighthouse on NE headland
      L.push(d( 2.8, -2.8, (c)      => S.rocks(c,  2.8, -2.8, pal, { scale: 1.5, flags })));
      L.push(d( 2.8, -2.7, (c, tt)  => S.lighthouse(c, 2.8, -2.95, pal, {}, tt)));

      // Harbour master / control tower
      L.push(d(-2.1,  0.9, (c, tt)  => S.controlTower(c, -2.1, 0.9, pal, { flags }, tt)));

      // Container yard — mid-island
      L.push(d(-0.5,  0.5, (c)      => S.containerStack(c, -0.5, 0.5, pal, { seed: 1 })));
      L.push(d( 0.9,  0.7, (c)      => S.containerStack(c,  0.9, 0.7, pal, { seed: 3 })));
      L.push(d( 0.1,  0.1, (c)      => S.containerStack(c,  0.1, 0.1, pal, { seed: 7, tall: true })));
      L.push(d( 1.7,  0.2, (c)      => S.containerStack(c,  1.7, 0.2, pal, { seed: 11 })));

      // Forklift working the yard
      L.push(d( 0.9,  1.5, (c)      => S.forklift(c, 0.9, 1.5, pal, {})));

      // Fuel storage silos (back-right)
      L.push(d( 2.7, -0.7, (c)      => S.silo(c, 2.7, -0.7, pal, { flags })));
      L.push(d( 3.2,  0.3, (c)      => S.silo(c, 3.2,  0.3, pal, { flags })));

      // Main quay dock
      L.push(d( 0.2,  3.6, (c)      => S.dock(c, 0.2, 3.6, pal, { w: 4.0, l: 2.3 })));

      // Standing crane over the quay
      L.push(d( 0.5,  2.8, (c, tt)  => S.portCrane(c, 0.5, 2.8, pal, {}, tt)));

      // Cargo ship at berth
      L.push(d( 1.7,  5.5, (c, tt)  => S.cargoShip(c, 1.7, 5.5, pal, {}, tt)));

      return L;
    },

    // No crop fields on transport island
    fields: [],

    // ---- capital catalogue items -------------------------------------
    items: [
      {
        id: 'transport.container_terminal', name: 'Container Terminal', cost: 85,
        mandatory: true, group: 'Capital equipment',
        desc: '+40 Cargo throughput',
        parts: (pal, flags, t) => [
          d(1.6, 1.8, (c, tt) => S.warehouse(c, 1.6, 1.8, pal, { flags })),
        ],
      },
      {
        id: 'transport.cargo_crane', name: 'Cargo Crane', cost: 60,
        mandatory: true, group: 'Capital equipment',
        desc: '+30 Lift capacity',
        parts: (pal, flags, t) => [
          d(-1.1, 3.4, (c, tt) => S.portCrane(c, -1.1, 3.4, pal, {}, tt)),
        ],
      },
      {
        id: 'transport.tugboat', name: 'Tugboat', cost: 45,
        mandatory: false, group: 'Capital equipment',
        desc: '+20 Marine towing capacity',
        parts: (pal, flags, t) => [
          d(-1.3, 5.6, (c, tt) => S.tugboat(c, -1.3, 5.6, pal, {}, tt)),
        ],
      },
      {
        id: 'transport.freight_depot', name: 'Freight Depot', cost: 70,
        mandatory: false, group: 'Capital equipment',
        desc: '+20 Land staging & storage',
        parts: (pal, flags, t) => [
          d(-2.4, -0.5, (c) => S.warehouse(c, -2.4, -0.5, pal, { flags })),
        ],
      },
      {
        id: 'transport.refrigerated_warehouse', name: 'Refrigerated Warehouse', cost: 90,
        mandatory: false, group: 'Capital equipment',
        desc: '+15 Cold-chain capacity',
        parts: (pal, flags, t) => [
          d(-1.7, -1.9, (c) => S.coldWarehouse(c, -1.7, -1.9, pal, { flags })),
        ],
      },
      {
        id: 'transport.truck_fleet', name: 'Heavy Truck Fleet', cost: 55,
        mandatory: false, group: 'Capital equipment',
        desc: '+25 Land transport capacity',
        parts: (pal, flags, t) => [
          d(2.1, 0.9, (c) => S.heavyTruck(c, 2.1, 0.9, pal, {})),
          d(2.7, 1.9, (c) => S.heavyTruck(c, 2.7, 1.9, pal, {})),
        ],
      },
      {
        id: 'transport.air_cargo', name: 'Air Cargo Pad', cost: 120,
        mandatory: false, group: 'Capital equipment',
        desc: '+15 Express delivery · enables air route',
        parts: (pal, flags, t) => [
          d(-0.6, -1.8, (c, tt) => S.helipad(c, -0.6, -1.8, pal, { flags }, tt)),
        ],
      },
      {
        id: 'common.kitchen', name: 'Kitchen', cost: 80,
        mandatory: false, group: 'Capital equipment',
        desc: 'Up to 6 Food/season for the workforce',
        parts: (pal, flags, t) => [
          d(-3.2, 2.9, (c, tt) => S.kitchenCottage(c, -3.2, 2.9, pal, { flags }, tt)),
        ],
      },
    ],
  };

  global.ISLANDS = global.ISLANDS || {};
  global.ISLANDS.transporter = TRANSPORT;
})(window);
