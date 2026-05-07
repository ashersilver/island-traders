SEASONS = ["Spring", "Summer", "Autumn", "Winter"]

CURRENCY_NAME   = "Dollop"   # singular
CURRENCY_PLURAL = "Dollops"  # plural
CURRENCY_SYMBOL = "Dp"       # display symbol

STARTING_DOLLOPS: float = 700.0   # CLI / test default (7 roles × 100 = 700 total)
TOTAL_STARTING_DOLLOPS: float = 700.0  # server overrides this via GameRoom.starting_capital
TOTAL_STARTING_POPULATION: int = 140  # 7 roles × 20

# Bootstrap inventory: each island starts with —
#   (a) one season's worth of its outputs, ready to sell in the opening round
#   (b) one season's worth of its production inputs, so it can produce round 2
# Anything beyond that must be purchased on the market.
STARTING_INVENTORY: dict[str, dict[str, int]] = {
    # Farmer: Spring outputs to sell + Spring inputs to produce next round
    "Farmer":        {"Food": 2, "Fish": 3,                          # to sell (Spring outputs)
                      "FarmMachinery": 1, "Oil": 2},                  # fuel buffer, not a season-proof stockpile
    # Miner: partial output to sell + inputs to produce (Oil serves both)
    "Miner":         {"Ore": 3, "Oil": 4,                            # to sell (Ore 3, Oil 3) + Oil 1 to produce
                      "Freight": 1, "MiningEquipment": 1},            # to produce
    # Transporter: cargo + seats to sell + Oil & Food to run services
    "Transporter":   {"Freight": 4, "PassengerSeats": 4,             # to sell
                      "Oil": 3, "Food": 1},                           # fuel-heavy role gets a larger opening buffer
    # Educator: Knowledge to sell + inputs to run the university
    "Educator":      {"Knowledge": 2,                                 # to sell
                      "CapitalEquipment": 1, "Finance": 1},           # to produce
    # Banker: Finance to sell + inputs to run the bank
    "Banker":        {"Finance": 2,                                   # to sell
                      "Knowledge": 1, "CapitalEquipment": 1},         # to produce
    # Manufacturer: FarmMachinery (default opening line) to sell + inputs to produce
    "Manufacturer":  {"FarmMachinery": 2,                             # to sell
                      "Ore": 2, "Oil": 2},                            # to produce; heavier lines still need more
    # Doctor: services to sell + inputs to operate
    "Doctor":        {"HealthServices": 2, "Vaccine": 1,             # to sell
                      "Knowledge": 1, "MedicalDevices": 1},           # to produce
}

# Dollops per unit at balanced supply/demand
BASE_PRICES: dict[str, float] = {
    "Food":                10.0,
    "Fish":                 8.0,
    "Ore":                 15.0,
    "Oil":                 20.0,
    "Freight":             12.0,
    "Knowledge":           18.0,
    "CapitalEquipment":    28.0,
    "Goods":               30.0,
    "HealthServices":      35.0,
    "Vaccine":             40.0,
    "Finance":             20.0,
    # ForgeHaven product lines
    "FarmMachinery":       32.0,   # tractors, ploughs, harvesters
    "MiningEquipment":     42.0,   # drills, excavators, ore separators
    "MedicalDevices":      50.0,   # surgical tools, dental equipment, scanners
    "TransportEquipment":  65.0,   # vehicles, ships, cranes (no freight surcharge)
    # Transporter services
    "PassengerSeats":      15.0,   # charter flight / passenger berth (per seat)
    # Educator IP
    "Patents":             80.0,   # one-time productivity boost (–20% input cost on chosen output)
}

# Units produced per season before event modifiers
# Farmer output is defined by FARMER_SEASONAL_CONVERSION instead.
# Manufacturer output is defined by MANUFACTURER_PRODUCT_LINES instead.
BASE_PRODUCTION: dict[str, dict[str, int]] = {
    "Miner":         {"Ore": 5, "Oil": 5},
    "Transporter":   {"Freight": 6, "PassengerSeats": 4},  # cargo + passenger services
    "Educator":      {"Knowledge": 4, "Patents": 1},       # 1 Patent/season baseline
    "Banker":        {"Finance": 3},
    "Doctor":        {"HealthServices": 4, "Vaccine": 1},
}

# Resources consumed each production cycle (base case; Farmer uses SEASONAL_CONVERSION;
# Manufacturer uses MANUFACTURER_PRODUCT_LINES keyed by chosen product line).
PRODUCTION_INPUTS: dict[str, dict[str, int]] = {
    "Farmer":        {"FarmMachinery": 1, "Oil": 1},          # machinery + fuel
    "Miner":         {"Oil": 1, "Freight": 1, "MiningEquipment": 1},
    "Transporter":   {"Oil": 2, "Food": 1},   # jet fuel (self-refined from Oil) + provisions
    "Educator":      {"CapitalEquipment": 1, "Finance": 1},   # equipment + operating budget
    "Banker":        {"Knowledge": 1, "CapitalEquipment": 1}, # expertise + infrastructure
    # Manufacturer has no single entry — see MANUFACTURER_PRODUCT_LINES
    "Doctor":        {"Knowledge": 1, "MedicalDevices": 1},
}

# Per-season input→output table for the Farmer island.
# Replaces PRODUCTION_INPUTS["Farmer"] + BASE_PRODUCTION["Farmer"] for that role.
# Inputs are consumed and outputs produced exactly as listed; workforce/event modifiers still apply.
FARMER_SEASONAL_CONVERSION: dict[str, dict] = {
    "Spring": {
        "inputs":  {"FarmMachinery": 1, "Oil": 1},
        "outputs": {"Food": 2, "Fish": 3},   # planting underway; good fishing
    },
    "Summer": {
        "inputs":  {"FarmMachinery": 1, "Oil": 1},
        "outputs": {"Food": 3, "Fish": 5},   # peak fishing; crops growing
    },
    "Autumn": {
        "inputs":  {"FarmMachinery": 1, "Oil": 1},
        "outputs": {"Food": 7, "Fish": 2},   # bumper harvest; fishing winds down
    },
    "Winter": {
        "inputs":  {"FarmMachinery": 1, "Oil": 1},
        "outputs": {"Food": 2, "Fish": 1},   # stores drawn down; minimal production
    },
}

# ForgeHaven (Manufacturer) produces one of four specialised product lines each season.
# The player (or AI) chooses which line to run at the start of production.
# Keys match ResourceType values for the output resource.
#
# Each entry:
#   inputs         – Ore and Oil consumed per production run
#   output         – resource type produced (str matching ResourceType value)
#   qty            – units produced per run (before event/workforce modifiers)
#   skilled        – skilled workers required (AssemblyWorker or Engineer)
#   unskilled      – unskilled workers required
#   freight_per_unit – Freight consumed to ship each unit produced (0 = no surcharge)
#   desc           – short human-readable label shown in CLI and export
MANUFACTURER_PRODUCT_LINES: dict[str, dict] = {
    "FarmMachinery": {
        "inputs":           {"Ore": 2, "Oil": 1},
        "output":           "FarmMachinery",
        "qty":              3,
        "skilled":          2,   # AssemblyWorkers to weld and fit
        "unskilled":        3,   # general labour for sub-assembly
        "freight_per_unit": 2,   # large steel frames; shipped on flatbeds
        "desc":             "Tractors & Farm Machinery",
    },
    "MiningEquipment": {
        "inputs":           {"Ore": 3, "Oil": 2},
        "output":           "MiningEquipment",
        "qty":              2,
        "skilled":          3,   # Engineers to spec heavy drilling rigs
        "unskilled":        2,
        "freight_per_unit": 3,   # heaviest line; specialist transport
        "desc":             "Mining Equipment",
    },
    "MedicalDevices": {
        "inputs":           {"Ore": 1, "Oil": 1},
        "output":           "MedicalDevices",
        "qty":              3,
        "skilled":          3,   # precision assembly; Engineers/AssemblyWorkers
        "unskilled":        1,   # minimal general labour
        "freight_per_unit": 1,   # small, high-value items
        "desc":             "Medical & Dental Devices",
    },
    "TransportEquipment": {
        "inputs":           {"Ore": 2, "Oil": 2},
        "output":           "TransportEquipment",
        "qty":              2,
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
STARTING_WORKFORCE: dict[str, int] = {
    "Farmer":        6,
    "Miner":         5,
    "Transporter":   4,
    "Educator":      3,
    "Banker":        3,
    "Manufacturer":  5,
    "Doctor":        6,    # 2 Doctors + 4 Nurses (scaled for board game)
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
    "Farmer":        [("Farmer", 1), ("Mechanic", 1), ("Veterinarian", 1)],
    "Miner":         [("Miner", 1), ("OilExtractionWorker", 1), ("Mechanic", 1)],
    "Transporter":   [("Engineer", 1), ("Mechanic", 1)],
    "Educator":      [("Professor", 1)],
    "Banker":        [("Banker", 1)],
    "Manufacturer":  [("Engineer", 1), ("AssemblyWorker", 1), ("Mechanic", 1)],
    "Doctor":        [("Doctor", 2), ("Nurse", 4)],    # exactly 6, no unskilled remainder
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
    "Farmer":       ["Farmer", "Veterinarian", "Mechanic"],
    "Miner":        ["Miner", "OilExtractionWorker", "RefinerySpecialist", "Mechanic"],
    "Transporter":  ["Engineer", "Mechanic"],
    "Educator":     ["Professor"],
    "Banker":       ["Banker"],
    "Manufacturer": ["AssemblyWorker", "Engineer", "Mechanic"],
    "Doctor":       ["Doctor", "Nurse"],
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
UNSKILLED_RECRUITMENT_RATIO: float = 0.5   # 1 recruitable worker per 2 unskilled residents

# ---------------------------------------------------------------------------
# University (Education Island) training capacity
# ---------------------------------------------------------------------------

# Maximum workers that can graduate into each profession per game YEAR.
UNIVERSITY_CAPACITY: dict[str, int] = {
    "Doctor":               2,
    "Nurse":               10,
    "Engineer":             2,
    "Farmer":               2,
    "Veterinarian":         1,
    "AssemblyWorker":      10,
    "Miner":                2,
    "OilExtractionWorker":  2,
    "RefinerySpecialist":   2,
    "Banker":               2,
    "Professor":            4,   # 1 per season × 4 seasons
    "Mechanic":             4,   # multi-island Technician (Apprenticeship pipeline)
}

# Professions that also have a per-SEASON cap (stricter than annual limit).
UNIVERSITY_SEASONAL_CAP: dict[str, int] = {
    "Professor": 1,   # no more than 1 Professor can graduate per season
}

# ---------------------------------------------------------------------------
# Training constants (legacy — superseded by UNIVERSITY_CAPACITY per profession)
# ---------------------------------------------------------------------------

# Units of Knowledge resource consumed to train one worker.
TRAINING_KNOWLEDGE_COST: int = 1

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
    "life":    25.0,    # per worker covered; pays LIFE_INSURANCE_DEATH_BENEFIT on death
    "medical": 30.0,    # flat per island; halves seasonal injury rate
}

# Dollops paid to the insured player per fatality (funded by the Banker).
LIFE_INSURANCE_DEATH_BENEFIT: float = 60.0

# Medical insurance reduces the effective injury_rate by this fraction.
MEDICAL_INSURANCE_INJURY_REDUCTION: float = 0.5
