SEASONS = ["Spring", "Summer", "Autumn", "Winter"]

CURRENCY_NAME   = "Dollop"   # singular
CURRENCY_PLURAL = "Dollops"  # plural
CURRENCY_SYMBOL = "Dp"       # display symbol

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

# Production is intentionally board-game chunky: one production action should
# create enough supply for the archipelago, not one sad little crate.
PRODUCER_PRODUCTIVITY_MULTIPLIER: int = 10

# Bootstrap inventory: each island starts with —
#   (a) one season's worth of its outputs, ready to sell in the opening round
#   (b) TWO seasons' worth of its production inputs, enough to produce through
#       Spring and Summer of Year 1 before needing to buy from other islands
# This gives every player breathing room to establish trade relationships.
STARTING_INVENTORY: dict[str, dict[str, int]] = {
    # Farmer: Spring outputs to sell + 2 seasons of inputs
    "Farmer":        {"Grain": 2, "Produce": 2, "Fish": 3, "Food": 15,  # to sell (Spring outputs) + Food buffer
                      "FarmMachinery": 2, "Oil": 2},                  # 2 seasons: 1 each per season
    # Miner: partial output to sell + 2 seasons of inputs
    "Miner":         {"Ore": 3, "Metal": 2, "Oil": 8,                # to sell + larger Oil buffer (self-consumed)
                      "Freight": 2, "MiningEquipment": 2},            # 2 seasons of each input
    # Transporter: cargo + seats to sell + 2 seasons of Oil & Food
    "Transporter":   {"Freight": 4, "PassengerSeats": 4,             # to sell
                      "Oil": 4, "Food": 2},                           # 2 seasons: Oil 2/s, Food 1/s
    # Educator: Expertise + Courses on hand so other islands can train in
    # Spring Y1 while the Expertise→Courses pipeline ramps (Phase 2).
    "Educator":      {"Expertise": 6,                                 # feeds Course production
                      "Courses": 5,                                    # classroom slots ready Y1
                      "LaboratoryEquipment": 2,                         # 2 seasons of Lab Equipment
                      "PassengerSeats": 10},                            # bootstraps cross-island training
    # Banker: no production output to stock; just the working knowledge they
    # need to write loans / underwrite insurance.  Banker income comes from
    # loan interest spread and insurance premiums — see island-ledger.md §3
    # for the full institutional-cash-pool model (future implementation).
    "Banker":        {"Expertise": 2},                                 # 2 seasons of expertise
    # Manufacturer: FarmMachinery (default opening line) to sell + 2 seasons of inputs
    "Manufacturer":  {"FarmMachinery": 2,                             # to sell
                      "Metal": 4, "Oil": 2},                          # 2 seasons: Metal 2/s, Oil 1/s
    # Doctor: services to sell + 2 seasons of inputs
    "Doctor":        {"HealthServices": 2, "Vaccine": 1,             # to sell
                      "Expertise": 2, "LaboratoryEquipment": 2},      # 2 seasons of each input
}

# Dollops per unit at balanced supply/demand
BASE_PRICES: dict[str, float] = {
    "Food":                10.0,
    "Fish":                 8.0,
    "Grain":                7.0,
    "Produce":              9.0,
    "Meat":                12.0,
    "Ore":                 12.0,
    "Metal":               20.0,
    "Oil":                 16.0,
    "Freight":             15.0,
    "Expertise":           18.0,
    "Courses":             25.0,   # classroom slots; gated by Expertise consumption
    "LaboratoryEquipment": 28.0,
    "Goods":               30.0,
    "HealthServices":      30.0,
    "Vaccine":             35.0,
    "Finance":             20.0,
    # ForgeHaven product lines
    "FarmMachinery":       45.0,   # tractors, ploughs, harvesters
    "MiningEquipment":     55.0,   # drills, excavators, ore separators
    "MedicalDevices":      50.0,   # surgical tools, dental equipment, scanners
    "TransportEquipment":  75.0,   # vehicles, ships, cranes (no freight surcharge)
    # Transporter services
    "PassengerSeats":      17.0,   # charter flight / passenger berth (per seat)
    # Educator IP
    "Patents":             50.0,   # one-time productivity boost (–20% input cost on chosen output)
}

# Units produced per season before event modifiers
# Farmer output is defined by FARMER_SEASONAL_CONVERSION instead.
# Manufacturer output is defined by MANUFACTURER_PRODUCT_LINES instead.
BASE_PRODUCTION: dict[str, dict[str, int]] = {
    "Miner":         {"Ore": 4 * PRODUCER_PRODUCTIVITY_MULTIPLIER,
                      "Metal": 2 * PRODUCER_PRODUCTIVITY_MULTIPLIER,
                      "Oil": 4 * PRODUCER_PRODUCTIVITY_MULTIPLIER},
    "Transporter":   {"Freight": 2.5 * PRODUCER_PRODUCTIVITY_MULTIPLIER,
                      "PassengerSeats": 0.75 * PRODUCER_PRODUCTIVITY_MULTIPLIER},
    "Educator":      {"Expertise": 4.5 * PRODUCER_PRODUCTIVITY_MULTIPLIER,
                      "Patents": 0.75 * PRODUCER_PRODUCTIVITY_MULTIPLIER},
    # Banker does NOT produce a "Finance" commodity — banking earns through
    # the spread on loans (and insurance premiums, future deal-guarantee
    # fees, brokerage, project finance).  Finance-as-tradeable-commodity
    # was a placeholder that made the Banker print money; removed so the
    # business model has to come from the actual lending engine.
    "Banker":        {},
    "Doctor":        {"HealthServices": 3 * PRODUCER_PRODUCTIVITY_MULTIPLIER,
                      "Vaccine": 0.75 * PRODUCER_PRODUCTIVITY_MULTIPLIER},
}

# Resources consumed each production cycle (base case; Farmer uses SEASONAL_CONVERSION;
# Manufacturer uses MANUFACTURER_PRODUCT_LINES keyed by chosen product line).
PRODUCTION_INPUTS: dict[str, dict[str, int]] = {
    "Farmer":        {"FarmMachinery": 1, "Oil": 1},          # machinery + fuel
    "Miner":         {"Oil": 1, "Freight": 1, "MiningEquipment": 1},
    "Transporter":   {"Oil": 2, "Food": 1},   # jet fuel (self-refined from Oil) + crew provisions
    "Educator":      {"LaboratoryEquipment": 1},               # labs (operating budget paid in Dp, not Finance commodity)
    # Banker has no per-season production input — they make money from loan
    # interest spread (and future deal-guarantee fees, brokerage, project
    # finance, insurance underwriting).  Expertise is still useful but is
    # not a hard requirement gating "production".
    "Banker":        {},
    # Manufacturer has no single entry — see MANUFACTURER_PRODUCT_LINES
    "Doctor":        {"Expertise": 1, "LaboratoryEquipment": 1},
}

# Per-season input→output table for the Farmer island.
# Replaces PRODUCTION_INPUTS["Farmer"] + BASE_PRODUCTION["Farmer"] for that role.
# Inputs are consumed and outputs produced exactly as listed; workforce/event modifiers still apply.
FARMER_SEASONAL_CONVERSION: dict[str, dict] = {
    "Spring": {
        "inputs":  {"FarmMachinery": 1, "Oil": 1},
        "outputs": {"Grain": 2 * PRODUCER_PRODUCTIVITY_MULTIPLIER,
                    "Produce": 2 * PRODUCER_PRODUCTIVITY_MULTIPLIER,
                    "Fish": 2 * PRODUCER_PRODUCTIVITY_MULTIPLIER},   # planting underway; good fishing
    },
    "Summer": {
        "inputs":  {"FarmMachinery": 1, "Oil": 1},
        "outputs": {"Grain": 3 * PRODUCER_PRODUCTIVITY_MULTIPLIER,
                    "Produce": 4 * PRODUCER_PRODUCTIVITY_MULTIPLIER,
                    "Fish": 4 * PRODUCER_PRODUCTIVITY_MULTIPLIER},   # peak fishing; crops growing
    },
    "Autumn": {
        "inputs":  {"FarmMachinery": 1, "Oil": 1},
        "outputs": {"Grain": 8 * PRODUCER_PRODUCTIVITY_MULTIPLIER,
                    "Produce": 6 * PRODUCER_PRODUCTIVITY_MULTIPLIER,
                    "Fish": 2 * PRODUCER_PRODUCTIVITY_MULTIPLIER},   # bumper harvest; fishing winds down
    },
    "Winter": {
        "inputs":  {"FarmMachinery": 1, "Oil": 1},
        "outputs": {"Grain": 3 * PRODUCER_PRODUCTIVITY_MULTIPLIER,
                    "Produce": 1 * PRODUCER_PRODUCTIVITY_MULTIPLIER,
                    "Fish": 1 * PRODUCER_PRODUCTIVITY_MULTIPLIER},   # stores drawn down; minimal production
    },
}

# ForgeHaven (Manufacturer) produces one of four specialised product lines each season.
# The player (or AI) chooses which line to run at the start of production.
# Keys match ResourceType values for the output resource.
#
# Each entry:
#   inputs         – Metal and Oil consumed per production run
#   output         – resource type produced (str matching ResourceType value)
#   qty            – units produced per run (before event/workforce modifiers)
#   skilled        – skilled workers required (AssemblyWorker or Engineer)
#   unskilled      – unskilled workers required
#   freight_per_unit – Freight consumed to ship each unit produced (0 = no surcharge)
#   desc           – short human-readable label shown in CLI and export
MANUFACTURER_PRODUCT_LINES: dict[str, dict] = {
    "FarmMachinery": {
        "inputs":           {"Metal": 2, "Oil": 1},
        "output":           "FarmMachinery",
        "qty":              3 * PRODUCER_PRODUCTIVITY_MULTIPLIER,
        "skilled":          2,   # AssemblyWorkers to weld and fit
        "unskilled":        3,   # general labour for sub-assembly
        "freight_per_unit": 2,   # large steel frames; shipped on flatbeds
        "desc":             "Tractors & Farm Machinery",
    },
    "MiningEquipment": {
        "inputs":           {"Metal": 3, "Oil": 2},
        "output":           "MiningEquipment",
        "qty":              2 * PRODUCER_PRODUCTIVITY_MULTIPLIER,
        "skilled":          3,   # Engineers to spec heavy drilling rigs
        "unskilled":        2,
        "freight_per_unit": 3,   # heaviest line; specialist transport
        "desc":             "Mining Equipment",
    },
    "LaboratoryEquipment": {
        "inputs":           {"Metal": 1, "Oil": 1},
        "output":           "LaboratoryEquipment",
        "qty":              3 * PRODUCER_PRODUCTIVITY_MULTIPLIER,
        "skilled":          3,
        "unskilled":        1,
        "freight_per_unit": 1,
        "desc":             "Laboratory Equipment",
    },
    "MedicalDevices": {
        "inputs":           {"Metal": 1, "Oil": 1},
        "output":           "MedicalDevices",
        "qty":              3 * PRODUCER_PRODUCTIVITY_MULTIPLIER,
        "skilled":          3,   # precision assembly; Engineers/AssemblyWorkers
        "unskilled":        1,   # minimal general labour
        "freight_per_unit": 1,   # small, high-value items
        "desc":             "Medical & Dental Devices",
    },
    "TransportEquipment": {
        "inputs":           {"Metal": 2, "Oil": 2},
        "output":           "TransportEquipment",
        "qty":              2 * PRODUCER_PRODUCTIVITY_MULTIPLIER,
        "skilled":          2,
        "unskilled":        3,
        "freight_per_unit": 0,   # self-propelled / delivered under own power
        "desc":             "Transportation Equipment",
    },
}

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
STARTING_WORKFORCE: dict[str, int] = {
    "Farmer":        6,
    "Miner":         5,
    "Transporter":   4,   # 1 Logistics Mgr + 3 Technicians (Flight/Seaman/Warehouse)
    "Educator":      11,  # 2 Prof + 4 Lect + 1 TD + 4 Instructor (bootstraps Manager-course capacity)
    "Banker":        4,   # 1 Banker + 2 Technicians (Analyst + Clerk) + 1 Unskilled
    "Manufacturer":  5,
    "Doctor":        6,   # 2 Doctors + 2 Nurses + 2 Medical Orderlies
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
# Doctor uses a custom mix (1 Doctor + 1 Nurse Manager + 3 Medical Orderlies + 1 Aide)
# but is currently encoded simply as 2 Doctors + 4 Nurses; revisit when Apprenticeship
# pipeline is implemented.
STARTING_WORKERS_BY_PROFESSION: dict[str, list[tuple[str, int]]] = {
    "Farmer":        [("Farmer", 1), ("Horticulturalist", 1), ("Veterinarian", 1)],
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
        ("BankingAnalyst", 1),       # Technician
        ("BankingClerk", 1),         # Technician
        # +1 Unskilled remainder (Receptionist)
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


# ---------------------------------------------------------------------------
# Banker capital-reserve / MBA leverage (economy-lifecycle Phase D)
# ---------------------------------------------------------------------------

# Reserve ratio applied to every loan the Banker issues — the share of
# the loan's principal that must come from the bank's OWN capital
# (locked until the loan resolves).  The remainder is sourced
# externally (depositors), invisible counterparties whose principal +
# the posted funding rate must be repaid at maturity (see
# `_fund_bank_external_portion`).
MBA_RESERVE_RATIO_BASE: float = 0.50       # < 3 MBA Banker Managers
MBA_RESERVE_RATIO_QUALIFIED: float = 0.20  # >= 3 MBA Banker Managers
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
    "Farmer":       ["Farmer", "FarmingTechnician", "Horticulturalist", "Veterinarian", "Mechanic"],
    "Miner":        ["Miner", "MiningTechnician", "OilExtractionWorker", "RefinerySpecialist", "Mechanic"],
    "Transporter":  [
        "LogisticsManager", "Engineer",
        "FlightCrew", "Seaman", "WarehouseManager", "Mechanic",
    ],
    "Educator":     ["Professor", "Lecturer", "TechnicalDirector", "Instructor"],
    "Banker":       ["Banker", "BankingAnalyst", "BankingClerk"],
    "Manufacturer": ["AssemblyWorker", "Engineer", "Mechanic"],
    "Doctor":       ["Doctor", "Nurse", "MedicalOrderly"],
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
# Board-game scale: 20 residents per island keeps recruitment tokens manageable.
STARTING_POPULATION: int = 20

# How many unskilled people can be drawn into the workforce per 2 unskilled residents.
# An island can employ up to this fraction of its current population as
# workers (skilled + unskilled).  Tightens recruit availability so the
# workforce can't outgrow the populace.
MAX_WORKFORCE_FRACTION_OF_POPULATION: float = 0.60

# ---------------------------------------------------------------------------
# University (Education Island) training capacity
# ---------------------------------------------------------------------------

# Maximum workers that can graduate into each profession per game YEAR.
UNIVERSITY_CAPACITY: dict[str, int] = {
    # Healthcare
    "Doctor":               2,
    "Nurse":               10,
    "MedicalOrderly":       8,    # apprenticeship-tier healthcare support
    # Engineering / cross-island
    "Engineer":             2,
    "Mechanic":             4,    # multi-island Technician (Apprenticeship pipeline)
    # Agriculture
    "Farmer":               2,
    "FarmingTechnician":    4,
    "Horticulturalist":      2,
    "Veterinarian":         1,
    # Manufacturing
    "AssemblyWorker":      10,
    # Mining
    "Miner":                2,
    "MiningTechnician":     4,
    "OilExtractionWorker":  2,
    "RefinerySpecialist":   2,
    # Banking
    "Banker":               2,
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
# Workplace risk constants
# ---------------------------------------------------------------------------
# Applied at the start of each season for high-hazard roles.
# injury_rate: fraction of active skilled workers who miss THIS season (lost-work-days).
# fatality_rate: probability per season that ONE skilled/experienced worker dies.
# Medical insurance halves injury_rate; Life insurance pays a death benefit on fatality.
WORKPLACE_RISK: dict[str, dict[str, float]] = {
    "Farmer":       {"injury_rate": 0.08, "fatality_rate": 0.04},   # machinery accidents
    "Miner":        {"injury_rate": 0.14, "fatality_rate": 0.08},   # collapses, gases
    "Transporter":  {"injury_rate": 0.07, "fatality_rate": 0.03},   # vehicle accidents
    "Manufacturer": {"injury_rate": 0.10, "fatality_rate": 0.05},   # industrial accidents
    # Low-risk roles — no workplace risk rolls applied
    "Educator":     {"injury_rate": 0.0,  "fatality_rate": 0.0},
    "Banker":       {"injury_rate": 0.0,  "fatality_rate": 0.0},
    "Doctor":       {"injury_rate": 0.0,  "fatality_rate": 0.0},
}

# Seasons a policy stays valid after purchase (4 = one full year).
INSURANCE_DURATION_SEASONS: int = 4

# Base annual premium per policy type.  Banker can charge more or less.
INSURANCE_BASE_PREMIUM: dict[str, float] = {
    "life":    50.0,    # per worker covered; pays LIFE_INSURANCE_DEATH_BENEFIT on death
    "medical": 60.0,    # flat per island; halves seasonal injury rate
}

# Dollops paid to the insured player per fatality (funded by the Banker).
LIFE_INSURANCE_DEATH_BENEFIT: float = 60.0

# Medical insurance reduces the effective injury_rate by this fraction.
MEDICAL_INSURANCE_INJURY_REDUCTION: float = 0.5
