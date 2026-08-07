# Canonical source of truth for the *running* application version.  Surfaced
# to the client via the /version HTTP endpoint and the initial game-state
# payload so playtesters can quote a version when reporting bugs.  Format is
# `MAJOR.MINOR.PATCH-dev.YYYY-MM-DD.N`; bump `.N` on each pre-release merge
# that's worth marking (see requirements/release-process.md → "Versioning").
#
# `pyproject.toml`'s `version` is intentionally different: it tracks the last
# *tagged* package release (currently 0.1.4) and is only bumped when cutting a
# release — dropping the `-dev.*` suffix as the dev series ships.  The two are
# reconciled at release time, not on every merge.
APP_VERSION: str = "0.1.6-dev.2026-08-06.1"

SEASONS = ["Spring", "Summer", "Autumn", "Winter"]

CURRENCY_NAME   = "Dollop"   # singular
CURRENCY_PLURAL = "Dollops"  # plural
CURRENCY_SYMBOL = "Dp"       # display symbol

# Central formula market-maker controls (P1, 2026-06-11).
# `current_price` remains the fair reference; formula-market buys pay the ask
# premium and formula-market sells receive the bid discount. Player order-book
# trades keep their posted prices.
MARKET_MAKER_SPREAD: float = 0.08
MARKET_MAKER_DEPTH_PER_RESOURCE: int = 50

# Per-season payroll by active-worker band (P2, 2026-06-11). Trainees and
# contracted-away staff are not active at home and are excluded.
PAYROLL_WAGE_BY_BAND: dict[str, float] = {
    "Worker": 0.25,
    "Technician": 0.5,
    "Manager": 1.0,
}

# Continuing education upkeep (P2b, 2026-07-05). Each island owes one unit of
# Expertise per active Manager-band worker over a rolling year.
CE_ANNUAL_PER_MANAGER: int = 1
CE_PENALTY_PER_SEASON: float = 0.05
CE_RECOVERY_PER_SEASON: float = 0.05
CE_MAX: float = 0.20

STARTING_DOLLOPS: float = 1500.0   # per-player default (economy-lifecycle Phase A; was 700)
TOTAL_STARTING_DOLLOPS: float = 10500.0  # 1500 × 7 players; server overrides via GameRoom.starting_capital
TOTAL_STARTING_POPULATION: int = 140  # 7 roles × 20

# Sustenance model (basket — 2026-05-25 redesign).  Each ``PEOPLE_PER_MEAL``
# residents consume one "meal" per season; a meal is satisfied by 1 Food OR
# (1 Grain + 1 Produce + 1 (Fish or Meat)), with cross-substitution at 2:1
# between raw ingredients.  Replaces the legacy ``BASE_POPULATION_SELF_FED``
# baseline — every resident now generates demand.  See
# ``Player.consume_sustenance`` for the allocator.
PEOPLE_PER_MEAL: int = 10

# Kitchen capital items (cash-only, all islands). Kitchens convert local raw
# ingredients into packaged Food once per season. "Protein" means Fish or Meat.
KITCHEN_ITEM_ID: str = "common.kitchen"
KITCHEN_SPECS: dict[str, dict] = {
    "common.kitchen": {
        "food_per_season": 10,
        "requires_chef": True,
        "recipe": {"Grain": 2, "Produce": 1, "Protein": 1},
    },
    "common.industrial_kitchen": {
        "food_per_season": 20,
        "requires_chef": False,
        "recipe": {"Grain": 1, "Produce": 0.5, "Protein": 0.5},
    },
}
KITCHEN_FOOD_PER_SEASON: int = KITCHEN_SPECS[KITCHEN_ITEM_ID]["food_per_season"]
KITCHEN_RECIPE: dict[str, float] = {
    "Grain": 2,
    "Produce": 1,
    "Protein": 1,  # Fish or Meat, chosen from local inventory.
}

# Production is intentionally board-game chunky: one production action should
# create enough supply for the archipelago, not one sad little crate.
PRODUCER_PRODUCTIVITY_MULTIPLIER: int = 10

# Bootstrap inventory: each island starts with —
#   (a) one season's worth of its outputs, ready to sell in the opening round
#   (b) TWO seasons' worth of its production inputs, enough to produce through
#       Spring and Summer of Year 1 before needing to buy from other islands
# This gives every player breathing room to establish trade relationships.
STARTING_INVENTORY: dict[str, dict[str, int]] = {
    # Farmer: Spring outputs to sell + 2 seasons of fuel. FarmMachinery is
    # durable capital now, not a consumable inventory buffer.
    "Farmer":        {"Grain": 2, "Produce": 2, "Fish": 3, "Food": 15,  # to sell (Spring outputs) + Food buffer
                      "Oil": 2},
    # Miner: partial output to sell + 2 seasons of consumable inputs.
    # MiningEquipment is durable capital now, not a consumable inventory buffer.
    "Miner":         {"Ore": 3, "Metal": 2, "Oil": 8,                # to sell + larger Oil buffer (self-consumed)
                      "Freight": 2},
    # Transporter: cargo + seats to sell + 2 seasons of Oil & Food
    "Transporter":   {"Freight": 4, "PassengerSeats": 4,             # to sell
                      "Oil": 4, "Food": 2},                           # 2 seasons: Oil 2/s, Food 1/s
    # Educator: Expertise + Courses on hand so other islands can train in
    # Spring Y1 while the Expertise→Courses pipeline ramps (Phase 2).
    "Educator":      {"Expertise": 7,                                 # feeds Course production and opening CE demand
                      "Courses": 5,                                    # classroom slots ready Y1
                      "Reagents": 2,                                   # 2 seasons of Reagents
                      "Oil": 2,                                        # building power + lab step buffer
                      "PassengerSeats": 10},                            # bootstraps cross-island training
    # Banker: no production output to stock; just the working knowledge they
    # need to write loans / underwrite insurance.  Banker income comes from
    # loan interest spread and insurance premiums — see island-ledger.md §3
    # for the full institutional-cash-pool model (future implementation).
    "Banker":        {"Expertise": 2, "Oil": 2},                      # knowledge + building power buffer
    # Manufacturer: FarmMachinery (default opening line) + Spares to sell,
    # plus 2 seasons of inputs.
    "Manufacturer":  {"FarmMachinery": 2, "Goods": 4, "Spares": 4,   # to sell
                      "Metal": 4, "Oil": 2},                          # 2 seasons: Metal 2/s, Oil 1/s
    # Doctor: services to sell + 2 seasons of inputs
    "Doctor":        {"MedicalSupplies": 2, "Vaccine": 1,             # to sell
                      "Expertise": 3, "Oil": 2, "Ore": 2},  # 2 seasons of inputs plus CE buffer (makes own Reagents)
}

# Dollops per unit at balanced supply/demand
BASE_PRICES: dict[str, float] = {
    "Food":                26.4,
    "Fish":                14.4,
    "Grain":               12.0,
    "Produce":             14.4,
    "Meat":                16.2,
    "Ore":                  4.5,
    "Metal":                8.0,
    "Oil":                  5.4,
    # Rebalance 2026-06-02: Freight/Seats up (Transporter was 553 Dp/s vs ~1300 avg);
    # MedicalSupplies/Vaccine down (Doctor was printing 31.5/36.75 vs Farmer 13.5/10.8);
    # Patents down (Educator Patent compounding at 47.5 Dp each dominated the sim).
    "Freight":             21.0,   # P3/#112 trims prior Transporter uplift
    "Expertise":           17.1,
    "Courses":             23.75,  # classroom slots; gated by Expertise consumption
    "Reagents":            28.0,
    "Goods":                5.0,
    "Spares":              12.0,   # repair kits; 2 Metal + 1 Oil input basis + margin
    "MedicalSupplies":      30.0,
    "Vaccine":             40.2,
    "Finance":             22.0,
    # ForgeHaven product lines
    "FarmMachinery":       60.0,   # installs as farmer.tractor capital
    "MiningEquipment":     70.0,   # installs as miner.excavator capital
    "MedicalDevices":      50.0,   # surgical tools, dental equipment, scanners
    "TransportEquipment":  75.0,   # vehicles, ships, cranes (no freight surcharge)
    # Transporter services
    "PassengerSeats":      23.0,   # #112 trims prior Transporter uplift
    # Educator IP
    "Patents":             32.0,   # was 47.5; curtail Patent compounding
}

# Units produced per season before event modifiers
# Farmer output is defined by FARMER_SEASONAL_CONVERSION instead.
# Manufacturer output is defined by MANUFACTURER_PRODUCT_LINES instead.
BASE_PRODUCTION: dict[str, dict[str, int]] = {
    "Miner":         {"Ore": 4 * PRODUCER_PRODUCTIVITY_MULTIPLIER,
                      "Metal": 2 * PRODUCER_PRODUCTIVITY_MULTIPLIER,
                      "Oil": 4.5 * PRODUCER_PRODUCTIVITY_MULTIPLIER},
    # Rebalance 2026-06-02 lifted Transporter output; #112 trims that uplift
    # after P3 demand made shipping overperform.
    "Transporter":   {"Freight": 3.25 * PRODUCER_PRODUCTIVITY_MULTIPLIER,
                      "PassengerSeats": 1.05 * PRODUCER_PRODUCTIVITY_MULTIPLIER},
    # Courses are classroom slots the Educator sells/uses for training.  They
    # are produced each season (scaled by workforce skill / capacity, so they
    # taper if the academic faculty is gutted) — previously they were absent
    # from production entirely, so the Educator spent the 5 starting slots and
    # could never make more, hard-stalling all training (playtest 2026-06).
    # Not multiplied by PRODUCER_PRODUCTIVITY_MULTIPLIER: a course is one
    # classroom (up to MAX_CLASS_SIZE_PER_COURSE trainees), not a bulk crate.
    # Rebalance 2026-06-10: Reagents no longer blanket-gate Education output,
    # so Expertise/Patents are trimmed while Courses stay at 4 to preserve
    # training throughput.
    "Educator":      {"Expertise": 1.2 * PRODUCER_PRODUCTIVITY_MULTIPLIER,
                      "Courses": 4,
                      "Patents": 0.10 * PRODUCER_PRODUCTIVITY_MULTIPLIER},
    # Banker rebalance 2026-06-02: small Finance production so the Banker has
    # some base value in the sim while the AI lending model is improved.
    # 0.5 × M = 5 units/season × 20 Dp = 100 Dp/s — just enough to be viable,
    # not enough to dominate.  (2 × M was too strong: Banker won 55% of sims.)
    "Banker":        {"Finance": 0.7 * PRODUCER_PRODUCTIVITY_MULTIPLIER},
    # Medical Sciences also produces Reagents (formerly the Manufacturer's
    # "LaboratoryEquipment") from Oil + Ore for sale to the Educator and its
    # own clinical use — 2026-06-02.  Modest, not the bulk x10 line.
    "Doctor":        {"MedicalSupplies": 3 * PRODUCER_PRODUCTIVITY_MULTIPLIER,
                      "Vaccine": 0.75 * PRODUCER_PRODUCTIVITY_MULTIPLIER,
                      "Reagents": 6},
}

# Resources consumed each production cycle (base case; Farmer uses SEASONAL_CONVERSION;
# Manufacturer uses MANUFACTURER_PRODUCT_LINES keyed by chosen product line).
PRODUCTION_INPUTS: dict[str, dict[str, int]] = {
    "Farmer":        {"Oil": 1},          # fuel; equipment is durable capital
    "Miner":         {"Oil": 1, "Freight": 1},
    "Transporter":   {"Oil": 2, "Food": 1},   # jet fuel (self-refined from Oil) + crew provisions
    "Educator":      {},
    # Banker has no per-season production input — they make money from loan
    # interest spread (and future deal-guarantee fees, brokerage, project
    # finance, insurance underwriting).  Expertise is still useful but is
    # not a hard requirement gating "production".
    "Banker":        {},
    # Manufacturer has no single entry — see MANUFACTURER_PRODUCT_LINES
    # Medical Sciences makes its own Reagents in-house from Oil + Ore (rather
    # than buying them), plus Expertise for clinical work (2026-06-02).
    "Doctor":        {"Expertise": 1, "Oil": 1, "Ore": 1},
}

# Inputs that gate only a specific output rather than the whole role's
# production run.  This keeps generic Education output classroom-based while
# preserving Reagents as the research input for Patents.
OUTPUT_PRODUCTION_INPUTS: dict[str, dict[str, dict[str, int]]] = {
    "Educator": {
        "Patents": {"Reagents": 1},
    },
    "Miner": {
        "Metal": {"Ore": 2, "Oil": 1},
    },
}

# Lab-scale output inputs. These are charged per completed output block, not
# as fixed per-season role inputs. Below the step size, classroom/base output
# stays free of lab consumables.
OUTPUT_PRODUCTION_INPUT_STEPS: dict[str, dict[str, dict]] = {
    "Educator": {
        "Courses": {"per_units": 10, "inputs": {"Reagents": 1, "Oil": 1}},
        "Expertise": {"per_units": 10, "inputs": {"Reagents": 1, "Oil": 1}},
    },
}

# Economic dependence P2a: all islands draw a flat building-power base, plus a
# surcharge for owned fixed, grid-powered heavy plant.
ENERGY_BASE: int = 1
ENERGY_DIVISOR: int = 4
BROWNOUT_CAPACITY_PENALTY: float = 0.10
BROWNOUT_QOL_PENALTY: int = 3
BANKER_OFFICE_GOODS_PER_SEASON: int = 1

# Per-season input→output table for the Farmer island.
# Replaces PRODUCTION_INPUTS["Farmer"] + BASE_PRODUCTION["Farmer"] for that role.
# Inputs are consumed and outputs produced exactly as listed; workforce/event modifiers still apply.
FARMER_SEASONAL_CONVERSION: dict[str, dict] = {
    "Spring": {
        "inputs":  {"Oil": 1},
        "outputs": {"Grain": round(2.4 * PRODUCER_PRODUCTIVITY_MULTIPLIER),
                    "Produce": round(2.4 * PRODUCER_PRODUCTIVITY_MULTIPLIER),
                    "Fish": round(2.4 * PRODUCER_PRODUCTIVITY_MULTIPLIER)},   # planting underway; good fishing
    },
    "Summer": {
        "inputs":  {"Oil": 1},
        "outputs": {"Grain": round(3.6 * PRODUCER_PRODUCTIVITY_MULTIPLIER),
                    "Produce": round(4.8 * PRODUCER_PRODUCTIVITY_MULTIPLIER),
                    "Fish": round(4.8 * PRODUCER_PRODUCTIVITY_MULTIPLIER)},   # peak fishing; crops growing
    },
    "Autumn": {
        "inputs":  {"Oil": 1},
        "outputs": {"Grain": round(9.6 * PRODUCER_PRODUCTIVITY_MULTIPLIER),
                    "Produce": round(7.2 * PRODUCER_PRODUCTIVITY_MULTIPLIER),
                    "Fish": round(2.4 * PRODUCER_PRODUCTIVITY_MULTIPLIER)},   # bumper harvest; fishing winds down
    },
    "Winter": {
        "inputs":  {"Oil": 1},
        "outputs": {"Grain": round(3.6 * PRODUCER_PRODUCTIVITY_MULTIPLIER),
                    "Produce": round(1.2 * PRODUCER_PRODUCTIVITY_MULTIPLIER),
                    "Fish": round(1.2 * PRODUCER_PRODUCTIVITY_MULTIPLIER)},   # stores drawn down; minimal production
    },
}

FARMER_HORTICULTURALIST_BONUS_MULTIPLIER: float = 1.35
FARMER_VETERINARIAN_BONUS_MULTIPLIER: float = 1.50
FARMER_FISH_WITHOUT_MARINE_BIOLOGIST_MULTIPLIER: float = 0.50
FISH_PROCESSING_TECHNICIANS_PER_BOAT: int = 2

MANUFACTURER_DURABLE_CAP_BASE: int = 6
MANUFACTURER_DURABLE_CAP_BONUS_PER_ITEM: int = 2
MANUFACTURER_DURABLE_CAP_MAX: int = 10
MANUFACTURER_DURABLE_OUTPUTS: tuple[str, ...] = (
    "FarmMachinery",
    "MiningEquipment",
    "TransportEquipment",
    "MedicalDevices",
)

# ForgeHaven (Manufacturer) produces one of four specialised product lines each season.
# The player (or AI) chooses which line to run at the start of production.
# Keys match ResourceType values for the output resource.
#
# Each entry:
#   inputs         – Metal and Oil consumed per production run
#   output         – resource type produced (str matching ResourceType value)
#   qty            – units produced per run (before event/workforce modifiers).
#                    Durable equipment lines are board-scale units; Goods
#                    remains a bulk commodity line.
#   skilled        – skilled workers required (AssemblyWorker or Engineer)
#   unskilled      – unskilled workers required
#   freight_per_unit – Freight consumed to ship each unit produced (0 = no surcharge)
#   desc           – short human-readable label shown in CLI and export
MANUFACTURER_PRODUCT_LINES: dict[str, dict] = {
    "FarmMachinery": {
        "inputs":           {"Metal": 2, "Oil": 1},
        "output":           "FarmMachinery",
        "qty":              4,
        "skilled":          2,   # AssemblyWorkers to weld and fit
        "unskilled":        3,   # general labour for sub-assembly
        "freight_per_unit": 1,   # durable board-scale unit; shipped on flatbeds
        "build_cost_dollops": 3.0,
        "desc":             "Tractors & Farm Machinery",
    },
    "Goods": {
        "inputs":           {"Metal": 1, "Oil": 1},
        "output":           "Goods",
        "qty":              5 * PRODUCER_PRODUCTIVITY_MULTIPLIER,
        "skilled":          2,
        "unskilled":        2,
        "freight_per_unit": 1,
        "build_cost_dollops": 0.2,
        "desc":             "Consumer Goods",
    },
    "MiningEquipment": {
        "inputs":           {"Metal": 3, "Oil": 2},
        "output":           "MiningEquipment",
        "qty":              3,
        "skilled":          3,   # Engineers to spec heavy drilling rigs
        "unskilled":        2,
        "freight_per_unit": 1,   # durable board-scale unit; specialist transport
        "build_cost_dollops": 4.0,
        "desc":             "Mining Equipment",
    },
    # Reagents (formerly "LaboratoryEquipment") moved to the Medical Sciences
    # island (Doctor), produced from Oil + Ore — see BASE_PRODUCTION/
    # PRODUCTION_INPUTS["Doctor"].  No longer a Manufacturer line (2026-06-02).
    "MedicalDevices": {
        "inputs":           {"Metal": 1, "Oil": 1},
        "output":           "MedicalDevices",
        "qty":              4,
        "skilled":          3,   # precision assembly; Engineers/AssemblyWorkers
        "unskilled":        1,   # minimal general labour
        "freight_per_unit": 1,   # durable board-scale unit; high-value items
        "build_cost_dollops": 3.0,
        "desc":             "Medical & Dental Devices",
    },
    "TransportEquipment": {
        "inputs":           {"Metal": 2, "Oil": 2},
        "output":           "TransportEquipment",
        "qty":              3,
        "skilled":          2,
        "unskilled":        3,
        "freight_per_unit": 0,   # self-propelled / delivered under own power
        "build_cost_dollops": 4.0,
        "desc":             "Transportation Equipment",
    },
    "Spares": {
        "inputs":           {"Metal": 2, "Oil": 1},
        "output":           "Spares",
        "qty":              4,
        "skilled":          1,   # Mechanic/AssemblyWorker
        "unskilled":        2,
        "freight_per_unit": 0,   # small parts; repair freight handles delivery
        "build_cost_dollops": 1.0,
        "desc":             "Equipment Spares Kits",
    },
}

# P3 consumer demand loop. Payroll accumulates in Player.household_cash; these
# constants convert resident cash into funded end-product purchases.
CONSUMER_GOODS_BASE_UNITS_PER_100_POP: int = 1
CONSUMER_FOOD_BASE_UNITS_PER_100_POP: int = 1
CONSUMER_GOODS_WEALTH_STEP_DOLLOPS: float = 1200.0
CONSUMER_GOODS_WEALTH_STEP_UNITS: int = 1
CONSUMER_GOODS_VOUCHER_PER_UNIT: float = 20.0
CONSUMER_STRUCTURAL_ADVISORY_WEIGHT: float = 0.4
CONSUMER_HEALTH_BASE_SEASONAL_UNITS: dict[str, int] = {
    "Summer": 1,
    "Winter": 1,
}
CONSUMER_HEALTH_CASUALTY_UNITS: int = 1
CONSUMER_VACCINE_SEASONAL_UNITS: dict[str, int] = {
    "Autumn": 1,
}
FLU_SEASON: str = "Winter"
FLU_STRAIN_LOSSES: tuple[float, ...] = (0.05, 0.10, 0.15, 0.20)
FLU_MAX_PRODUCTIVITY_LOSS: float = 0.20
VACCINE_PEOPLE_PER_DOSE: int = 20
VACCINE_INFECTION_REDUCTION: float = 0.80

# Quality of Life + Pollution (#48 / #45).
QOL_WEIGHT_FOOD: float = 0.50
QOL_WEIGHT_HEALTH: float = 0.25
QOL_WEIGHT_POLLUTION: float = 0.20
QOL_WEIGHT_FOREST: float = 0.05
OIL_POLLUTION_SCALE: float = 50.0
POLLUTION_HEALTH_MITIGATION: float = 0.50
QOL_BIRTH_RATE_MIN: float = 0.50
QOL_BIRTH_RATE_MAX: float = 2.00
QOL_EMIGRATION_THRESHOLD: float = 0.20
QOL_EMIGRATION_RATE: float = 0.04
CONSUMER_EDUCATION_SEASONAL_UNITS: dict[str, int] = {
    "Spring": 1,
    "Summer": 1,
    "Autumn": 1,
    "Winter": 1,
}
CONSUMER_EDUCATION_VOUCHER_PER_UNIT: float = 20.0
HOUSEHOLD_ACTIVITY_STIMULUS_PER_CAPITA: float = 0.1
CONSUMER_DELIVERY_FREIGHT_FEE_PER_UNIT: float = 8.0
FREIGHT_UNITS_PER_TRADE_UNIT: float = 0.1
FREIGHT_FEE_PER_TRADE_UNIT: float = 1.0

# Medical response + seasonal QoL (2026-07-04 medical brief).
DOCTOR_TREATMENTS_PER_SEASON: int = 3
NURSE_TREATMENTS_PER_SEASON: int = 2
UNTREATED_RECOVERY_SEASONS: int = 2
TREATED_RECOVERY_SEASONS: int = 1
MEDEVAC_SEATS: int = 2
MEDEVAC_FEE: float = 8.0
NURSE_UPKEEP_SUPPLIES: int = 1
NURSE_QOL_WORKFORCE_COVERAGE: int = 15
NURSE_QOL_BONUS_CAP_POINTS: float = 15.0
NURSE_PRODUCTIVITY_BONUS_CAP: float = 0.20
MEDICAL_SUPPLIES_STOCKPILE_PEOPLE_PER_UNIT: int = 10
QOL_PRODUCTIVITY_MIN: float = 0.85
QOL_PRODUCTIVITY_MAX: float = 1.15

# Business cycle + severity-scaled disasters (2026-07-04 brief).
PANDEMIC_DURATION_SEASONS: int = 2
VACCINE_PANDEMIC_SIDELINE_REDUCTION: float = 0.80
SEVERITY_PROFILES: dict[str, dict[str, float]] = {
    "Minor": {
        "yield_penalty": 0.0,
        "damage_bonus": 0,
        "workforce_sidelined_fraction": 0.10,
        "capital_failure_multiplier": 1.5,
        "pandemic_yield_modifier": 0.50,
        "pandemic_sidelined_fraction": 0.20,
        "rebuild_levy_fraction": 0.05,
    },
    "Major": {
        "yield_penalty": 0.25,
        "damage_bonus": 1,
        "workforce_sidelined_fraction": 0.20,
        "capital_failure_multiplier": 2.5,
        "pandemic_yield_modifier": 0.40,
        "pandemic_sidelined_fraction": 0.35,
        "rebuild_levy_fraction": 0.10,
    },
    "Catastrophic": {
        "yield_penalty": 1.0,
        "damage_bonus": 2,
        "workforce_sidelined_fraction": 0.35,
        "capital_failure_multiplier": 4.0,
        "pandemic_yield_modifier": 0.25,
        "pandemic_sidelined_fraction": 0.50,
        "rebuild_levy_fraction": 0.20,
    },
}
REBUILD_LEVY_MIN_DOLLOPS: float = 20.0
REBUILD_LEVY_INSTALLMENTS: int = 2
ENERGY_CRISIS_OIL_PRICE_MULTIPLIER: float = 2.0
ENERGY_CRISIS_DURATION_SEASONS: int = 2
HARBOUR_BLOCKADE_FREIGHT_PRICE_MULTIPLIER: float = 3.0
BABY_BOOM_POPULATION_GROWTH_MULTIPLIER: float = 2.0
BABY_BOOM_QOL_STABILITY_DELTA: int = 5

# How strongly prices respond to supply/demand imbalance
PRICE_ELASTICITY: float = 0.3

MIN_PRICE_MULTIPLIER: float = 0.2
MAX_PRICE_MULTIPLIER: float = 5.0

# ---------------------------------------------------------------------------
# Workforce constants
# ---------------------------------------------------------------------------

# How many workers each role needs per season (affects production output).
# Shortfall scales production down proportionally.
SEASONAL_WORKFORCE: dict[str, dict[str, int]] = {
    "Farmer":        {"Spring": 4, "Summer": 6, "Autumn": 8, "Winter": 2},
    "Miner":         {"Spring": 5, "Summer": 5, "Autumn": 5, "Winter": 4},
    "Transporter":   {"Spring": 4, "Summer": 5, "Autumn": 6, "Winter": 3},
    "Educator":      {"Spring": 4, "Summer": 2, "Autumn": 4, "Winter": 4},
    "Banker":        {"Spring": 3, "Summer": 3, "Autumn": 4, "Winter": 3},
    "Manufacturer":  {"Spring": 5, "Summer": 5, "Autumn": 5, "Winter": 4},
    # Healthcare: peaks in Winter (illness) and Summer (injuries/accidents).
    "Doctor":        {"Spring": 5, "Summer": 6, "Autumn": 5, "Winter": 8},
}

# Seasonal base-yield multiplier applied to BASE_PRODUCTION before event and workforce modifiers.
# Each role's values average to 1.0 across the four seasons so annual output is unchanged.
# The Farmer is excluded here — its output is fully governed by FARMER_SEASONAL_CONVERSION.
SEASONAL_YIELD: dict[str, dict[str, float]] = {
    #                       Spring  Summer  Autumn  Winter
    "Miner":        {"Spring": 1.0, "Summer": 1.1, "Autumn": 1.0, "Winter": 0.9},
    "Transporter":  {"Spring": 0.9, "Summer": 1.1, "Autumn": 1.2, "Winter": 0.8},
    "Educator":     {"Spring": 1.1, "Summer": 0.7, "Autumn": 1.1, "Winter": 1.1},
    "Banker":       {"Spring": 0.9, "Summer": 1.0, "Autumn": 1.2, "Winter": 0.9},
    "Manufacturer": {"Spring": 1.0, "Summer": 1.0, "Autumn": 1.1, "Winter": 0.9},
    "Doctor":       {"Spring": 0.9, "Summer": 1.1, "Autumn": 0.9, "Winter": 1.1},
}

# Starting total workers per role (see STARTING_WORKERS_BY_PROFESSION for detail).
# Invariant: every island starts with at least 1 Manager + 2 Technicians.
# Each island starts with 50 workers (2026-06-02 playtest ask): the skilled
# breakdown in STARTING_WORKERS_BY_PROFESSION is seeded first, and the
# remainder up to 50 fills in as Unskilled — giving a deep unskilled bench
# (~40) so production/training labour requests (sometimes up to ~10 unskilled)
# can always be met.  NOTE: total is scaled by 7/num_players in Game.setup, so
# a full 7-player game gets exactly 50 per island.
STARTING_WORKFORCE: dict[str, int] = {
    "Farmer":        50,
    "Miner":         50,
    "Transporter":   50,
    "Educator":      50,
    "Banker":        50,
    "Manufacturer":  50,
    "Doctor":        50,
}

# Fraction of starting workers who begin with training_level >= 1.
STARTING_TRAINED_FRACTION: dict[str, float] = {
    "Farmer":        0.50,
    "Miner":         0.40,
    "Transporter":   0.50,
    "Educator":      0.70,
    "Banker":        0.67,
    "Manufacturer":  0.40,
    "Doctor":        1.00,   # all 6 are trained professionals (Doctors/Nurses)
}

# Profession breakdown for starting workforce.
# Each entry is a list of (profession_name, count) pairs.
# Remaining workers up to STARTING_WORKFORCE total are added as Unskilled.
#
# Default mix per requirements/production-capacity-model.md §5:
#   1 Manager + 2 Technicians + 3 Workers (= 6 starting workforce)
# Doctor uses a custom mix encoded as 2 Doctors + 2 Nurses + 2 Medical Orderlies
# (6 total) — matches the Doctor block below, STARTING_TRAINED_FRACTION = 1.00,
# and RULES.md. Revisit if the Apprenticeship pipeline reshapes the medical tiers.
STARTING_WORKERS_BY_PROFESSION: dict[str, list[tuple[str, int]]] = {
    "Farmer":        [
        ("Farmer", 1),
        ("Horticulturalist", 1),
        ("Veterinarian", 1),
        ("Marine Biologist", 1),
        ("Fish Processing Technician", 2),
    ],
    "Miner":         [("Miner", 1), ("MiningTechnician", 1), ("OilExtractionWorker", 1)],
    "Transporter":   [
        ("LogisticsManager", 1),     # Manager
        ("FlightCrew", 1),           # Technician
        ("Seaman", 1),               # Technician
        ("WarehouseManager", 1),     # Technician (ground ops supervisor)
    ],
    "Educator":      [
        # Bootstrap-aware shape: training a Lecturer is itself a Manager-tier
        # course (Lecturer is Manager-band), and the staffing rule requires
        # an existing Lecturer to run any Manager-tier course.  Starting with
        # zero Lecturers is a permanent chicken-and-egg deadlock — fresh games
        # could never train a first Lecturer.  Option B (2 Prof + 4 Lect + 1 TD
        # + 4 Instructor) keeps the academic faculty viable from turn 1 with
        # a realistic Professor-to-Lecturer ratio (lecturers do the front-line
        # teaching; professors supervise) while keeping the Technical pipeline
        # at the same 1 TD + 4 Instructor + Workshop-prerequisite baseline.
        ("Professor", 2),            # Manager — supervises 4 concurrent Manager courses
        ("Lecturer", 4),             # Manager — runs 4 concurrent Manager courses
        ("TechnicalDirector", 1),    # Manager — supervises 2 concurrent Technical courses
        ("Instructor", 4),           # Technician — runs 4 concurrent Technical courses
        # Total: 11.  Manager capacity = min(2*2, 4) = 4.  Technical capacity
        # = min(1*2, 4, workshop_slots) (workshop is now mandatory-minimum, +3).
    ],
    "Banker":        [
        ("Banker", 1),               # Manager
        ("Lawyer", 1),               # Manager — in-house counsel (#44 lease gate)
        ("Actuary", 1),              # Technician — insurance underwriting
        ("BankingAnalyst", 1),       # Technician
        ("BankingClerk", 1),         # Technician
    ],
    "Manufacturer":  [("Engineer", 1), ("AssemblyWorker", 1), ("Mechanic", 1)],
    "Doctor":        [
        ("Doctor", 2),               # Manager
        ("Nurse", 2),                # Manager (was 4)
        ("MedicalOrderly", 2),       # Technician (new — meets ≥2T invariant)
    ],
}

# ---------------------------------------------------------------------------
# Worker lifecycle (economy-lifecycle Phase B)
# ---------------------------------------------------------------------------

# Working life in seasons per worker band; a worker retires (is removed
# from the roster — the seat must be re-recruited + retrained) once their
# age reaches this.  First-cut tunable (accepted 2026-05-19).
WORKING_LIFE_SEASONS: dict[str, int] = {
    "Manager":    40,   # ~10 years
    "Technician": 32,   # ~8 years
    "Worker":     24,   # ~6 years (Unskilled)
}
DEFAULT_WORKING_LIFE_SEASONS: int = 32

# Bootstrap seeding: starting workers of (role → profession) begin this
# many seasons *from retirement* (seed age = working_life(band) − value).
# Phase B activates Agriculture only; other islands default to age 0.
# This is also the model's near-retirement balance lever.
STARTING_WORKER_AGES: dict[str, dict[str, int]] = {
    "Farmer": {
        "Farmer":          4,   # Manager ~1 year from retirement
        "Horticulturalist": 8,  # Technician ~2 years from retirement
    },
}


# ---------------------------------------------------------------------------
# Capital lifecycle (economy-lifecycle Phase C)
# ---------------------------------------------------------------------------

# Default service life for any CapitalItem that doesn't override it.
# 20 seasons ≈ 5 years.  Tunable (accepted first-cut).
DEFAULT_SERVICE_LIFE_SEASONS: int = 20

# Per-season maintenance rule of thumb when a CapitalItem's
# `maintenance_per_season` is 0.0 (no override): charge this fraction of
# the item's purchase cost per owned unit per season.  Tunable.
DEFAULT_MAINTENANCE_FRACTION: float = 0.03

# Equipment warranty + failure model (#130, 2026-06-12; #188 failure curve
# 2026-06-21).  Warranties are sold by the Manufacturer and charged annually.
# Unwarranted equipment rolls a failure check every season on the #188
# per-quarter Weibull schedule; failed units need paid repair parts plus
# Freight spares delivery before they contribute capacity again.
EQUIPMENT_WARRANTY_ANNUAL_RATE: float = 0.20
# Per-quarter Weibull failure probability (#188).  Each entry is the chance an
# uninsured unit fails during that quarter of its life (Q1 = first season
# owned).  Rolled every season using the unit's current quarter; for ages
# beyond Q20 the last value is held.  Supersedes the old annual age-bucket
# table {1: 0.05, 2: 0.15, 3: 0.40}.
EQUIPMENT_FAILURE_PROB_BY_QUARTER: dict[int, float] = {
    1: 0.0470,  2: 0.0509,  3: 0.0551,  4: 0.0596,  5: 0.0644,
    6: 0.0696,  7: 0.0751,  8: 0.0810,  9: 0.0873, 10: 0.0940,
    11: 0.1012, 12: 0.1088, 13: 0.1169, 14: 0.1256, 15: 0.1348,
    16: 0.1446, 17: 0.1550, 18: 0.1661, 19: 0.1778, 20: 0.1902,
}
# Multiplier applied to the per-quarter failure probability for events such as
# natural disasters (earthquake, flood) and sabotage during strikes (#188).
# Default 1.0 (no event); the engine exposes a seam to raise it.
EQUIPMENT_FAILURE_EVENT_MULTIPLIER: float = 1.0
# Repair/parts fee on failure as a fraction of the unit's purchase value
# ($35 per $100 basis, #188; was 0.50 under the old straw-man model).
EQUIPMENT_FAILURE_REPAIR_FRACTION: float = 0.35
# A spares kit on hand cuts a repair bill in half (#185: "each kit reduces
# repair costs by 50%").  Without a pre-stocked spare the baseline fraction
# above applies (spares are manufactured at failure time).
EQUIPMENT_SPARES_REPAIR_DISCOUNT: float = 0.5
# #188 maintenance / warranty contract cost per $100 of equipment value, by
# term in years: (baseline, with Predictive Maintenance).  Charged ONCE upfront
# on a #185 order (not recurring); covers the unit until the term lapses, after
# which it becomes failure-eligible again.  Replaces the flat recurring premium
# for contracted units.
EQUIPMENT_MAINTENANCE_CONTRACT_PER_100: dict[int, tuple[float, float]] = {
    1: (8.62, 7.11),
    2: (19.90, 14.82),
    3: (35.70, 23.94),
    4: (55.29, 34.88),
    5: (78.23, 47.91),
}
EQUIPMENT_REPAIR_SHIP_FREIGHT: int = 1
EQUIPMENT_REPAIR_AIR_FREIGHT: int = 2
EQUIPMENT_AI_WARRANTY_MIN_COST: float = 0.0
# Referral kickback paid to the Manufacturer (by the Bank) when a capital order
# is financed — origination incentive for steering the deal through financing.
MANUFACTURER_FINANCE_REFERRAL_RATE: float = 0.02
# A Manufacturer ordering manufactured equipment from itself pays this fraction
# of list price as a sunk cash cost (no markup, no counterparty — Wave 5.3);
# the manufactured inputs are still consumed.  Spares kits are added at cost.
MANUFACTURER_SELF_ORDER_PRICE_FRACTION: float = 0.20
# Capital orders take a deposit up front (Wave 9): the buyer puts this fraction
# of the agreed total down when ordering, which is applied against the balance
# on delivery.  A buyer who cannot pay the balance forfeits the deposit to the
# Manufacturer, who keeps the finished goods and may resell them at list price.
# The deposit is refunded in full if the order ends without a build (the
# Manufacturer declines, or the buyer cancels before production starts).
CAPITAL_ORDER_DEPOSIT_FRACTION: float = 0.50


# ---------------------------------------------------------------------------
# Banker capital-reserve / MBA leverage (economy-lifecycle Phase D)
# ---------------------------------------------------------------------------

# Reserve ratio applied to every loan the Banker issues — the share of
# the loan's principal that must come from the bank's OWN capital
# (locked until the loan resolves).  The remainder is sourced
# externally (depositors), invisible counterparties whose principal +
# the posted funding rate must be repaid at maturity (see
# `_fund_bank_external_portion`).
MBA_RESERVE_RATIO_BASE: float = 0.05       # < 3 MBA Banker Managers
MBA_RESERVE_RATIO_QUALIFIED: float = 0.02  # >= 3 MBA Banker Managers
# How many MBA-qualified Banker Managers it takes to drop the ratio.
MBA_QUALIFIED_THRESHOLD: int = 3

# Starting *aged* capital: role → list of (item_id, count, age_in_seasons).
# Seeds the island with a pre-existing unit already part-aged so it must
# be replaced from the Manufacturer within its remaining life.  Phase C
# activates Agriculture only (the combine harvester); other islands
# default to no aged seed.  Generalises as a bootstrap balance lever.
STARTING_AGED_CAPITAL: dict[str, list[tuple[str, int, int]]] = {
    "Farmer": [
        # Combine harvester (`farmer.harvester`, 8-season life) 4 seasons
        # old at start → expires end of Year 1 (aligns with the seeded
        # Farmer's retirement to create a real double squeeze).
        ("farmer.harvester", 1, 4),
    ],
    "Manufacturer": [
        # Starting spares storage (2026-06-22): lets Forge hold 10 generic
        # spares from turn one without making the opening-invest screen pay
        # for baseline warehouse infrastructure.
        ("manufacturer.small_warehouse", 1, 0),
    ],
}

# Baseline (non-seasonal) skilled and unskilled worker requirements per production cycle.
# "Skilled" means a worker whose profession appears in SKILLED_PROFESSIONS for that role.
# The seasonal SEASONAL_WORKFORCE totals scale these requirements up/down by season.
LABOUR_REQUIREMENTS: dict[str, dict[str, int]] = {
    "Farmer":       {"skilled": 2, "unskilled": 2},   # Farmer specialists + general hands
    "Miner":        {"skilled": 2, "unskilled": 2},   # Miners/drillers + surface crew
    "Transporter":  {"skilled": 2, "unskilled": 2},   # Engineers + loaders/stevedores
    "Educator":     {"skilled": 2, "unskilled": 1},   # Professors + admin staff
    "Banker":       {"skilled": 2, "unskilled": 1},   # Bankers + clerical support
    # Manufacturer labour comes from MANUFACTURER_PRODUCT_LINES per chosen line
    "Manufacturer": {"skilled": 2, "unskilled": 2},   # fallback; overridden by product line
    "Doctor":       {"skilled": 2, "unskilled": 2},   # Doctors/Nurses + orderlies
}

# Profession names that qualify as "skilled" for each island's labour calculation.
# All active workers whose profession is NOT in this list count toward the unskilled slot.
# This is the legacy two-tier classification — see WorkerBand for the new three-band
# (Manager / Technician / Worker) classification used by the production capacity model.
SKILLED_PROFESSIONS: dict[str, list[str]] = {
    "Farmer":       [
        "Farmer", "FarmingTechnician", "Horticulturalist", "Veterinarian",
        "Marine Biologist", "Fish Processing Technician", "Mechanic", "Chef", "Lawyer",
    ],
    "Miner":        [
        "Miner", "MiningTechnician", "MiningForeman",
        "OilExtractionWorker", "RefinerySpecialist", "Mechanic", "Chef", "Lawyer",
    ],
    "Transporter":  [
        "LogisticsManager", "Engineer",
        "FlightCrew", "Seaman", "WarehouseManager", "Mechanic", "Chef", "Lawyer",
    ],
    "Educator":     ["Professor", "Lecturer", "TechnicalDirector", "Instructor", "Chef", "Lawyer"],
    "Banker":       ["Banker", "Actuary", "BankingAnalyst", "BankingClerk", "Chef", "Lawyer"],
    "Manufacturer": ["FactoryForeman", "Tradesman", "AssemblyWorker", "Engineer", "Mechanic", "Chef", "Lawyer"],
    "Doctor":       ["Doctor", "Nurse", "MedicalResearcher", "MedicalTechnician", "MedicalOrderly", "Chef", "Lawyer"],
}

# ---------------------------------------------------------------------------
# Production capacity constants
# ---------------------------------------------------------------------------

# Minimum effective workforce factor guaranteed by the island's physical
# infrastructure (buildings, machinery, established routes, etc.).
STARTING_PRODUCTION_CAPACITY: dict[str, float] = {
    "Farmer":        0.60,
    "Miner":         0.50,
    "Transporter":   0.65,
    "Educator":      0.55,
    "Banker":        0.70,
    "Manufacturer":  0.50,
    "Doctor":        0.55,
}

# ---------------------------------------------------------------------------
# Population constants
# ---------------------------------------------------------------------------

# Total island population at game start (includes employed workers + unskilled population).
# Board-game scale: 50 residents per island.  With the 0.60 workforce cap
# (MAX_WORKFORCE_FRACTION_OF_POPULATION) this allows the workforce to expand
# up to 0.60 × 50 = 30 workers.
STARTING_POPULATION: int = 50

# How many unskilled people can be drawn into the workforce per 2 unskilled residents.
# An island can employ up to this fraction of its current population as
# workers (skilled + unskilled).  Tightens recruit availability so the
# workforce can't outgrow the populace.
MAX_WORKFORCE_FRACTION_OF_POPULATION: float = 0.60

# Fraction of the population the starting workforce represents (2026-07-01
# playtest ask: "workers should no longer include the whole population").
# Applied as Game.setup's `workforce_scale`, which uniformly scales both
# STARTING_WORKFORCE totals and each named profession's seed count in
# STARTING_WORKERS_BY_PROFESSION — so the calibrated manager/technician/worker
# *ratios* for each role (e.g. Educator's Professor/Lecturer bootstrap mix)
# are preserved, only the absolute headcount shrinks. Previously this was a
# hardcoded workforce_scale = 1.0 (100% — the whole population was workforce).
WORKFORCE_PARTICIPATION_RATE: float = 0.50

# ---------------------------------------------------------------------------
# Graceful degradation (GitHub #47 + 2026-05-27 playtest)
# ---------------------------------------------------------------------------
# When an island runs short of required expertise, production used to drop
# to zero — leading to cascading failures (Manny Fracture: Mining at 0
# active workers for 5 years → no Oil → all Manufacturer lines locked at
# max 0).  These floors keep a starved island producing SOMETHING so the
# market can still trade and recovery is possible.
#
# Floors are SAFETY NETS, not ceilings: the natural labour-productivity
# factor still wins when higher.  Only kicks in when the natural factor
# would otherwise be lower than the floor.
#
# Within a single role, floors COMPOSE MULTIPLICATIVELY across bands
# (e.g. a Farmer missing both the Farmer specialist AND all Farming
# Technicians produces at 0.10 × 0.50 = 0.05).
#
# Across roles (multi-role players), the MIN floor applies — multi-role
# expertise gaps are tracked the same way the underlying productivity
# factor sums them across roles.
EXPERTISE_DEGRADATION_FLOORS: dict[str, float] = {
    # Gentle safety-net floors (2026-07-12 calibration for GitHub #47):
    # the ONLY job here is to stop a fully-missing-expertise line from
    # hard-stopping at exactly zero.  Kept low so the floor barely
    # re-prices the economy — the spec 0.10/0.25/0.50 values shifted
    # Educator -4.6 / Manufacturer -3.7 / Doctor +3.8 pts (well past the
    # ±2σ gate); these values keep the floor while holding all roles
    # inside the gate.  See requirements/expertise-degradation-floor-2026-07-12.md.
    "unique_specialist": 0.05,
    "manager":           0.10,
    "technician":        0.20,
    "unskilled":         1.00,  # no floor change — existing behaviour
}

# Master switch for the graceful-degradation floor.  2026-05-27
# investigation: turning on the floor (even at tiny 0.02/0.05/0.10
# values) shocked the 4-seed calibration sweep — Miner dropped to 4.4%
# and Banker to 2.8% in their win-rate from the documented 13.1% /
# 14.8% baseline.  Root cause: existing balance depends on
# cascading-collapse positive-feedback loops (one role's failure
# cascading to consumers is what gives high-risk roles their scarcity
# premium).  Any non-zero floor prevents this cascade and re-prices the
# whole economy.
#
# Disabled until the proper calibration pass happens.  The constants
# and ProductionEngine.expertise_degradation_floor helper are in place
# so a future calibration work can flip this flag and tune the floors,
# but the application code in _labour_productivity_factor checks this
# flag before applying — default behaviour is unchanged.
EXPERTISE_DEGRADATION_ENABLED: bool = True

# Primary Manager-tier "unique specialist" per role.  Losing this triggers
# the harshest (0.10) floor.
UNIQUE_SPECIALIST_PROFESSION: dict[str, str] = {
    "Farmer":       "Farmer",
    "Miner":        "Miner",
    "Educator":     "Professor",
    "Banker":       "Banker",
    "Manufacturer": "Engineer",
    "Doctor":       "Doctor",
    "Transporter":  "LogisticsManager",
}

# Per-role override if a specific island needs a different floor than the
# defaults above.  Empty by default; populate during playtest calibration
# if specific roles feel wrong.
EXPERTISE_DEGRADATION_ROLE_OVERRIDES: dict[str, dict[str, float]] = {}

# ---------------------------------------------------------------------------
# University (Education Island) training capacity
# ---------------------------------------------------------------------------

# Maximum workers that can graduate into each profession per game YEAR.
UNIVERSITY_CAPACITY: dict[str, int] = {
    # Healthcare
    "Doctor":               2,
    "Nurse":               10,
    "MedicalResearcher":     2,
    "MedicalTechnician":     8,
    "MedicalOrderly":       8,    # apprenticeship-tier healthcare support
    # Engineering / cross-island
    "Engineer":             2,
    "Mechanic":             4,    # multi-island Technician (Apprenticeship pipeline)
    # Agriculture
    "Farmer":               2,
    "Marine Biologist":     2,
    "FarmingTechnician":    4,
    "Fish Processing Technician": 8,
    "Horticulturalist":      2,
    "Veterinarian":         1,
    # Manufacturing
    "FactoryForeman":      4,
    "Tradesman":           10,
    "AssemblyWorker":      10,
    # Mining
    "Miner":                2,
    "MiningTechnician":     4,
    "MiningForeman":        3,
    "OilExtractionWorker":  2,
    "RefinerySpecialist":   2,
    # Banking
    "Banker":               2,
    "Actuary":              4,
    "BankingAnalyst":       4,
    "BankingClerk":         6,
    # Education
    "Professor":            4,    # 1 per season × 4 seasons
    "Lecturer":             4,
    "TechnicalDirector":    4,
    "Instructor":           6,
    # Transport (the new professions added with the workforce baseline rule)
    "LogisticsManager":     2,
    "FlightCrew":           6,
    "Seaman":               6,
    "WarehouseManager":     6,
    # Cross-island sustenance support
    "Chef":                 7,
    # Cross-island legal counsel (#44) — required to write a new equipment lease
    "Lawyer":               2,
}

# Professions that also have a per-SEASON cap (stricter than annual limit).
UNIVERSITY_SEASONAL_CAP: dict[str, int] = {
    "Professor": 1,   # no more than 1 Professor can graduate per season
}

# ---------------------------------------------------------------------------
# Training constants (legacy — superseded by UNIVERSITY_CAPACITY per profession)
# ---------------------------------------------------------------------------

# Units of Expertise resource consumed to train one worker.
TRAINING_EXPERTISE_COST: int = 1

# A Course is a classroom slot, not a per-student token.  Up to this many
# trainees can share one Course; larger batches consume ceil(n / cap)
# Courses on Educator approval (Education Model Phase 2).
MAX_CLASS_SIZE_PER_COURSE: int = 12

# Per-trainee food & accommodation cost while at the Education Island,
# charged per season at college (Education Model Phase 3 fee component).
TRAINEE_FOOD_ACCOM_PER_SEASON: float = 5.0

# ---------------------------------------------------------------------------
# Population / birth rate constants
# ---------------------------------------------------------------------------

# Base annual birth rate for all islands (2% per year).
# Actual rate = BASE_BIRTH_RATE * (1 - wealth_ratio), so richer islands grow slower.
BASE_BIRTH_RATE: float = 0.02

# ---------------------------------------------------------------------------
# Passenger transport constants
# ---------------------------------------------------------------------------

# A charter flight costs this fraction of the primary fee (training or medical).
FLIGHT_COST_FRACTION: float = 0.20

# Cargo vessels carry this many passengers for free (no Transporter fee needed).
# Passengers via cargo arrive one full season later than via flight or Transporter.
CARGO_FREE_PASSENGERS: int = 2
CARGO_TRANSIT_SEASONS: int = 1   # extra seasons of absence when travelling by cargo

# ---------------------------------------------------------------------------
# Event frequency cap (2026-05-27 event-frequency-cap brief)
# ---------------------------------------------------------------------------
# Maximum production-halting events any single player can suffer per game
# year.  A halt event is one with outage=True OR yield_modifier<=0.1 (see
# EventResult.is_halt_event).  Soft damage (yield ~0.5) is uncapped.  When
# a player has used their budget and draws another halt, the resolver
# re-rolls avoiding halts.  Addresses the "5 production-halting events in
# 5 consecutive seasons" reports (Comet 1 #9, AyaySir BUG-08).
HALT_EVENTS_PER_PLAYER_PER_YEAR: int = 1

# ---------------------------------------------------------------------------
# Worker repurposing (2026-05-28)
# ---------------------------------------------------------------------------
# Cost in Dollops to reassign one worker to a new profession.  The worker
# loses all training_level and experience but immediately joins the new
# role at unskilled level.  Reflects retraining overhead / disruption cost.
REPURPOSE_WORKER_COST: float = 25.0

# ---------------------------------------------------------------------------
# Medical staffing contracts (2026-05-28)
# ---------------------------------------------------------------------------
# Any island can hire Doctors or Nurses from the Healthcare island on a
# short-term contract.  Staff must travel via PassengerSeats (round-trip:
# staff_count × 2 seats total).
#
# STAFFING_BASE_FEE_PER_STAFF_PER_SEASON — suggested default fee (Dollops)
# per staff member per season when the player hasn't set their own price.
#
# STAFFING_FOOD_PER_STAFF_PER_SEASON — extra Food/meals the host island
# must provide for each visiting staff member or visiting trainee each season
# (in addition to their standard workforce sustenance).
#
# STAFFING_MAX_DURATION_SEASONS — upper bound on any single contract
# (prevents staff from being away indefinitely).
STAFFING_BASE_FEE_PER_STAFF_PER_SEASON: float = 20.0
STAFFING_FOOD_PER_STAFF_PER_SEASON: float = 0.2
STAFFING_MAX_DURATION_SEASONS: int = 4

# ---------------------------------------------------------------------------
# Workplace risk constants
# ---------------------------------------------------------------------------
# Applied at the start of each season for high-hazard roles.
# injury_rate: fraction of active skilled workers who miss THIS season (lost-work-days).
# fatality_rate: probability per season that ONE skilled/experienced worker dies.
# Medical insurance halves injury_rate; Life insurance pays a death benefit on fatality.
WORKPLACE_RISK: dict[str, dict[str, float]] = {
    "Farmer":       {"injury_rate": 0.035, "fatality_rate": 0.012},  # machinery accidents
    "Miner":        {"injury_rate": 0.060, "fatality_rate": 0.025},  # collapses, gases
    "Transporter":  {"injury_rate": 0.030, "fatality_rate": 0.010},  # vehicle accidents
    "Manufacturer": {"injury_rate": 0.045, "fatality_rate": 0.018},  # industrial accidents
    # Low-risk roles still carry a small background workplace risk so the
    # productive islands are not uniquely exposed to workforce attrition.
    "Educator":     {"injury_rate": 0.005, "fatality_rate": 0.001},
    "Banker":       {"injury_rate": 0.005, "fatality_rate": 0.001},
    "Doctor":       {"injury_rate": 0.005, "fatality_rate": 0.001},
}

# Seasons a policy stays valid after purchase (4 = one full year).
INSURANCE_DURATION_SEASONS: int = 4

# Base annual premium per policy type.  Banker can charge more or less.
INSURANCE_BASE_PREMIUM: dict[str, float] = {
    "life":    50.0,    # per worker covered; pays LIFE_INSURANCE_DEATH_BENEFIT on death
    "medical": 60.0,    # flat per island; halves seasonal injury rate
}

# Per-head medical premium (2026-06-02): medical policies now cover a specified
# number of workers/students and are priced per head for the policy term.  Used
# both when the Banker sells a sized policy and when the Education island
# auto-provisions cover for incoming students.  Tunable in calibration.
MEDICAL_PREMIUM_PER_HEAD: float = 8.0  # Dp per covered head for the full term

# Internal underwriting cost paid by the Banker when issuing an insurance
# policy. Requires an Actuary on staff.
ACTUARIAL_EVALUATION_COST: float = 5.0

# Dollops paid to the insured player per fatality (funded by the Banker).
# Doubled 2026-05-27 from 60 to 120 to offset the Banker calibration
# spike from LIFE_INSURANCE_FATALITY_REDUCTION: fewer fatalities means
# Banker pays out the death benefit less often, which pushed Banker
# win rate +6 pp out of band.  Higher per-death payout balances total
# expected Banker liability while making the policy more valuable to
# the bereaved island.
LIFE_INSURANCE_DEATH_BENEFIT: float = 120.0

# Medical insurance reduces the effective injury_rate by this fraction.
MEDICAL_INSURANCE_INJURY_REDUCTION: float = 0.5

# Life insurance reduces the effective fatality_rate by this fraction
# (mirroring the medical-injury reduction).  Before this constant
# existed, Life insurance only paid a death benefit AFTER the worker
# died — the player could not prevent fatalities, only get cash.  Now
# the rate itself is halved when a policy is in force, so insured
# islands have a real chance to retain experienced workers.
# 2026-05-27 disaster-mitigation brief.
LIFE_INSURANCE_FATALITY_REDUCTION: float = 0.5

# Hard cap on the fraction of an island's active workforce that can be
# lost to fatality in a single workplace-risk tick.  Even with the
# Life-insurance fatality reduction above, an unlucky cascade of rolls
# could still wipe most of a small starting workforce in one season —
# this cap keeps the island from going from fully-staffed to skeleton
# in a single tick.  At 30% of N active workers (min 1), a 5-worker
# Miner can lose at most 1 per tick; a 10-worker workforce loses at
# most 3.  Surviving workers may still die on later ticks.
# 2026-05-27 disaster-mitigation brief.
MAX_WORKFORCE_LOSS_PER_TICK_FRACTION: float = 0.30
