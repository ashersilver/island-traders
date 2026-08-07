"""
Capital equipment catalogue and per-output production recipes.

Tabular data driving the production capacity model. Edit here to tune:
  - which items each role can buy in the Investing Phase / mid-game,
  - how much each output unit costs in inputs and labour.

Numbers are first-pass drafts from `requirements/production-capacity-model.md`.
"""
from __future__ import annotations

from .models.capacity import CapitalItem, ProductionRecipe

CAPACITY_PRODUCTIVITY_MULTIPLIER: int = 10


# ---------------------------------------------------------------------------
# Capital equipment catalogue — buyable items per role
# ---------------------------------------------------------------------------

CAPITAL_CATALOGUE: list[CapitalItem] = [
    # ----- Universal -------------------------------------------------------
    CapitalItem(
        item_id="common.kitchen",
        name="Kitchen",
        role="Any",
        cost=80.0,
        delivery_seasons=0,
        effects={"kitchen_food_per_season": 10, "cash_only": True},
        description="Chef-staffed kitchen: converts raw ingredients into up to 10 Food/season",
        service_life_seasons=12,
        capacity_units=1,
    ),
    CapitalItem(
        item_id="common.industrial_kitchen",
        name="Industrial Kitchen",
        role="Any",
        cost=150.0,
        delivery_seasons=1,
        effects={"kitchen_food_per_season": 20, "cash_only": True},
        description="Industrial kitchen: converts raw ingredients into up to 20 Food/season, no Chef required",
        capacity_units=2,
    ),
    CapitalItem(
        item_id="common.laboratory_equipment",
        name="Laboratory Equipment",
        role="Any",
        cost=40.0,
        delivery_seasons=1,
        # Durable soil/sample-testing kit (NOT the consumable Reagents).  Lifts
        # output capacity for the islands that test soil/samples — Agriculture,
        # Mining, Medical (2026-06-02).  Only the outputs an island actually
        # produces are affected.
        effects={"cash_only": True, "capacity": {
            "Grain": 2, "Produce": 2, "Food": 2,   # Agriculture
            "Ore": 2,                               # Mining
            "MedicalSupplies": 2, "Vaccine": 1,      # Medical
        }},
        description="Soil/sample testing: +2 capacity to Agriculture, Mining & Medical outputs",
        capacity_units=1,
    ),

    # ----- Farmer ----------------------------------------------------------
    CapitalItem(
        item_id="farmer.tractor",
        name="Tractor",
        role="Farmer",
        cost=60.0,
        delivery_seasons=0,
        effects={"capacity": {"Grain": 10, "Produce": 6}},
        description="+10 Grain, +6 Produce capacity",
        capacity_units=1,
    ),
    CapitalItem(
        item_id="farmer.harvester",
        name="Combine Harvester",
        role="Farmer",
        cost=90.0,
        delivery_seasons=2,
        effects={"capacity": {"Grain": 6, "Produce": 4}, "labour_relief": {"Technician": 1}},
        description="+6 Grain, +4 Produce, -1 Technician need (~2-year service life, must be replaced)",
        # Phase C: shorter life than the default 20 — a combine wears out fast.
        service_life_seasons=8,
        capacity_units=2,
    ),
    CapitalItem(
        item_id="farmer.fishing_boat",
        name="Fishing Boat",
        role="Farmer",
        cost=50.0,
        delivery_seasons=0,
        effects={"capacity": {"Fish": 4}},
        description="+4 Fish capacity",
        capacity_units=1,
    ),
    CapitalItem(
        item_id="farmer.livestock_barn",
        name="Livestock Barn",
        role="Farmer",
        cost=70.0,
        delivery_seasons=0,
        effects={"capacity": {"Meat": 4}},
        description="+4 Meat capacity",
        capacity_units=2,
    ),
    CapitalItem(
        item_id="farmer.industrial_kitchen",
        name="Industrial Kitchen",
        role="Farmer",
        cost=75.0,
        delivery_seasons=0,
        effects={"capacity": {"Food": 6}},
        description="+6 packaged Food capacity",
        capacity_units=1,
    ),
    CapitalItem(
        item_id="farmer.storage_building",
        name="Storage Building",
        role="Farmer",
        cost=40.0,
        delivery_seasons=0,
        effects={"inventory_cap": 10},
        description="+10 inventory cap",
        capacity_units=1,
    ),

    # ----- Miner -----------------------------------------------------------
    CapitalItem(
        item_id="miner.excavator",
        name="Excavator",
        role="Miner",
        cost=70.0,
        delivery_seasons=0,
        effects={"capacity": {"Ore": 4}},
        description="+4 Ore capacity",
        capacity_units=2,
        energy_intensive=True,
    ),
    CapitalItem(
        item_id="miner.crusher",
        name="Crusher",
        role="Miner",
        cost=50.0,
        delivery_seasons=0,
        effects={"capacity": {"Ore": 2, "Metal": 2}, "input_relief": {"Ore": {"Oil": 0.2}}},
        description="+2 Ore, +2 Metal, –0.2 Oil per Ore",
        capacity_units=1,
        energy_intensive=True,
    ),
    CapitalItem(
        item_id="miner.enhanced_crusher_smelter",
        name="Enhanced Crusher and Smelter",
        role="Miner",
        cost=140.0,
        delivery_seasons=2,
        effects={
            "capacity": {"Metal": 6},
            "metal_productivity_multiplier": 3.0,
            "metal_oil_multiplier": 0.5,
        },
        description="+200% Metal productivity, -50% Oil per Metal",
        capacity_units=3,
        energy_intensive=True,
    ),
    CapitalItem(
        item_id="miner.oil_rig",
        name="Oil Rig",
        role="Miner",
        cost=110.0,
        delivery_seasons=2,
        effects={"capacity": {"Oil": 4}},
        description="+4 Oil capacity",
        capacity_units=3,
        energy_intensive=True,
    ),
    CapitalItem(
        item_id="miner.refinery",
        name="Refinery",
        role="Miner",
        cost=100.0,
        delivery_seasons=2,
        effects={"capacity": {"Oil": 2}, "enables_profession": "RefinerySpecialist"},
        description="+2 Oil, enables RefinerySpecialist multiplier",
        capacity_units=3,
        energy_intensive=True,
    ),

    # ----- Transporter -----------------------------------------------------
    CapitalItem(
        item_id="transporter.cargo_ship",
        name="Cargo Ship",
        role="Transporter",
        cost=80.0,
        delivery_seasons=0,
        effects={"capacity": {"Freight": 12}},
        description="+12 Freight capacity",
        capacity_units=3,
    ),
    CapitalItem(
        item_id="transporter.cargo_plane",
        name="Cargo Plane",
        role="Transporter",
        cost=130.0,
        delivery_seasons=2,
        effects={"capacity": {"Freight": 8}, "fast": True},
        description="+8 Freight (fast)",
        capacity_units=4,
    ),
    CapitalItem(
        item_id="transporter.passenger_liner",
        name="Passenger Liner",
        role="Transporter",
        cost=90.0,
        delivery_seasons=0,
        effects={"capacity": {"PassengerSeats": 5}},
        description="+5 PassengerSeats",
        capacity_units=3,
    ),
    CapitalItem(
        item_id="transporter.passenger_plane",
        name="Passenger Plane",
        role="Transporter",
        cost=140.0,
        delivery_seasons=2,
        effects={"capacity": {"PassengerSeats": 5}, "fast": True},
        description="+5 PassengerSeats (fast)",
        capacity_units=4,
    ),

    # ----- Educator --------------------------------------------------------
    CapitalItem(
        item_id="educator.lecture_hall",
        name="Lecture Hall",
        role="Educator",
        cost=50.0,
        delivery_seasons=0,
        effects={"capacity": {"Expertise": 4, "Courses": 4}, "education_slots": 2},
        description="+4 Expertise, +4 Courses, +2 Education slots",
        capacity_units=1,
    ),
    CapitalItem(
        item_id="educator.library",
        name="Library",
        role="Educator",
        cost=40.0,
        delivery_seasons=0,
        effects={"capacity": {"Expertise": 2, "Patents": 1}},
        description="+2 Expertise, +1 Patent",
        capacity_units=1,
    ),
    CapitalItem(
        item_id="educator.research_lab",
        name="Research Lab",
        role="Educator",
        cost=100.0,
        delivery_seasons=2,
        effects={"capacity": {"Patents": 3}, "research_stock_per_season": 2},
        description="+3 Patent capacity, generates Research stock",
        capacity_units=4,
        energy_intensive=True,
    ),
    CapitalItem(
        item_id="educator.computer_cluster",
        name="Computer Cluster",
        role="Educator",
        cost=80.0,
        delivery_seasons=2,
        effects={"capacity": {"Patents": 1}, "input_relief": {"Expertise": {"Reagents": 0.2}}},
        description="+1 Patent, -0.2 Reagents per Expertise",
        capacity_units=1,
        energy_intensive=True,
    ),
    CapitalItem(
        item_id="educator.technical_workshop",
        name="Technical Workshop",
        role="Educator",
        cost=60.0,
        delivery_seasons=0,
        # Per workshop: up to 6 technician trainees in training at a time.
        # Tracked per-trainee (sum of in-flight Technician-tier batch sizes),
        # NOT per-course — the workshop is a physical-plant headcount cap.
        effects={"technical_workshop_trainees": 6},
        description="+6 Technical Workshop trainee seats (prerequisite for technical-tier courses)",
        capacity_units=1,
        lease_terms={"term_years": 3, "residual_fraction": 0.25, "rate_margin": 0.02},
    ),

    # ----- Banker ----------------------------------------------------------
    # Capital items now express headroom for Loans and InsurancePolicies
    # (the Banker's actual business activities) rather than a "Finance"
    # commodity capacity, which is no longer produced.
    CapitalItem(
        item_id="banker.vault",
        name="Vault",
        role="Banker",
        cost=60.0,
        delivery_seasons=0,
        effects={"capacity": {"Loans": 4}},
        description="+4 Loans capacity",
        capacity_units=1,
    ),
    CapitalItem(
        item_id="banker.trading_floor",
        name="Trading Floor",
        role="Banker",
        cost=70.0,
        delivery_seasons=0,
        effects={"capacity": {"Loans": 3, "InsurancePolicies": 1}},
        description="+3 Loans, +1 InsurancePolicy",
        capacity_units=1,
    ),
    CapitalItem(
        item_id="banker.underwriting_desk",
        name="Underwriting Desk",
        role="Banker",
        cost=50.0,
        delivery_seasons=0,
        effects={"capacity": {"InsurancePolicies": 3}},
        description="+3 InsurancePolicies capacity",
        capacity_units=1,
    ),
    CapitalItem(
        item_id="banker.reinsurance_treaty",
        name="Reinsurance Treaty",
        role="Banker",
        cost=100.0,
        delivery_seasons=2,
        effects={"fatality_payout_multiplier": 0.5},
        description="–50% fatality payout cost",
        capacity_units=2,
    ),

    # ----- Manufacturer ----------------------------------------------------
    CapitalItem(
        item_id="manufacturer.foundry",
        name="Foundry",
        role="Manufacturer",
        cost=80.0,
        delivery_seasons=0,
        effects={
            "unlocks_lines": ["FarmMachinery", "MiningEquipment"],
            "capacity": {"FarmMachinery": 3, "MiningEquipment": 2},
        },
        description="enables FarmMachinery + MiningEquipment lines",
        capacity_units=1,
        energy_intensive=True,
    ),
    CapitalItem(
        item_id="manufacturer.assembly_line",
        name="Assembly Line",
        role="Manufacturer",
        cost=70.0,
        delivery_seasons=0,
        effects={
            "line_throughput_bonus": 1,
            "capacity": {
                "FarmMachinery": 1,
                "Goods": 5,
                "MiningEquipment": 1,
                "MedicalDevices": 1,
                "TransportEquipment": 1,
                "Spares": 4,
            },
        },
        description="+1 unit/season on any line",
        capacity_units=1,
        energy_intensive=True,
    ),
    CapitalItem(
        item_id="manufacturer.small_warehouse",
        name="Small Spares Warehouse",
        role="Manufacturer",
        cost=30.0,
        delivery_seasons=0,
        effects={"spares_storage": 10, "maintenance_free": True},
        description="+10 Spares storage capacity",
        capacity_units=1,
    ),
    CapitalItem(
        item_id="manufacturer.warehouse",
        name="Spares Warehouse",
        role="Manufacturer",
        cost=50.0,
        delivery_seasons=0,
        effects={"spares_storage": 12},
        description="+12 Spares storage capacity",
        capacity_units=1,
    ),
    CapitalItem(
        item_id="manufacturer.precision_workshop",
        name="Precision Workshop",
        role="Manufacturer",
        cost=100.0,
        delivery_seasons=2,
        effects={"unlocks_lines": ["MedicalDevices"], "capacity": {"MedicalDevices": 3}},
        description="enables MedicalDevices line",
        capacity_units=2,
        energy_intensive=True,
    ),
    CapitalItem(
        item_id="manufacturer.shipyard",
        name="Shipyard",
        role="Manufacturer",
        cost=120.0,
        delivery_seasons=2,
        effects={"unlocks_lines": ["TransportEquipment"], "capacity": {"TransportEquipment": 2}},
        description="enables TransportEquipment line",
        capacity_units=4,
        energy_intensive=True,
    ),

    # ----- Doctor ----------------------------------------------------------
    CapitalItem(
        item_id="doctor.hospital_ward",
        name="Hospital Ward",
        role="Doctor",
        cost=60.0,
        delivery_seasons=0,
        effects={"capacity": {"MedicalSupplies": 4}},
        description="+4 MedicalSupplies capacity",
        capacity_units=2,
    ),
    CapitalItem(
        item_id="doctor.operating_theatre",
        name="Operating Theatre",
        role="Doctor",
        cost=100.0,
        delivery_seasons=2,
        effects={"capacity": {"MedicalSupplies": 2, "Vaccine": 1}},
        description="+2 MedicalSupplies, +1 Vaccine",
        capacity_units=3,
        energy_intensive=True,
    ),
    CapitalItem(
        item_id="doctor.vaccine_lab",
        name="Vaccine Lab",
        role="Doctor",
        cost=110.0,
        delivery_seasons=2,
        effects={"capacity": {"Vaccine": 2}},
        description="+2 Vaccine capacity",
        capacity_units=2,
        energy_intensive=True,
    ),
    CapitalItem(
        item_id="doctor.cold_chain_storage",
        name="Cold Chain Storage",
        role="Doctor",
        cost=40.0,
        delivery_seasons=0,
        effects={"vaccine_persistence": True},
        description="Vaccine doesn't expire between seasons",
        capacity_units=1,
        energy_intensive=True,
    ),
    # 2026-06-02: Reagents are made on the Medical island from Oil + Ore but
    # had no capital item dedicated to their capacity — players saw a vague
    # "Capital Equipment" hint with no catalogue option.  The Reagent Lab
    # is the dedicated piece of plant.  Modest, fast delivery so it can be
    # bought in the opening investing window.
    # #26: the Pathology Lab is the plant behind Laboratory Tests — metal
    # assays, soil analyses, and later environmental assessments and health
    # certificates.  In the Doctor's mandatory minimum so assay supply exists
    # from turn 1; without it the island has zero Lab Test capacity and every
    # other island eats the un-assayed yield penalty with nothing to buy.
    CapitalItem(
        item_id="doctor.pathology_lab",
        name="Pathology Lab",
        role="Doctor",
        cost=75.0,
        delivery_seasons=0,
        effects={"capacity": {"LaboratoryTests": 3}},
        description="Assay bench: metal assays, soil analyses and health certificates",
        capacity_units=1,
    ),
    CapitalItem(
        item_id="doctor.reagent_lab",
        name="Reagent Lab",
        role="Doctor",
        cost=70.0,
        delivery_seasons=1,
        effects={"capacity": {"Reagents": 6}},
        description="Chemistry plant: turns Oil+Ore into Reagents (+capacity)",
        capacity_units=1,
    ),
]


# ---------------------------------------------------------------------------
# Per-unit production recipes
# ---------------------------------------------------------------------------

PRODUCTION_RECIPES: list[ProductionRecipe] = [
    # ----- Farmer ----------------------------------------------------------
    ProductionRecipe(
        role="Farmer", output="Grain",
        inputs={"Oil": 5 / 6},
        manager_per_unit=0.1, technician_per_unit=0.4, worker_per_unit=1.0,
        description="Farm equipment fuel (halved 2026-06-04 playtest balance)",
    ),
    ProductionRecipe(
        role="Farmer", output="Fish",
        inputs={"Oil": 5 / 3},
        manager_per_unit=0.1, technician_per_unit=0.4, worker_per_unit=1.0,
        description="Fishing fleet fuel (halved 2026-06-04 playtest balance)",
    ),
    ProductionRecipe(
        role="Farmer", output="Produce",
        inputs={"Oil": 2.5},
        manager_per_unit=0.1, technician_per_unit=0.4, worker_per_unit=1.0,
        description="Field produce; Horticulturalists improve the line (oil halved 2026-06-04)",
    ),
    ProductionRecipe(
        role="Farmer", output="Meat",
        inputs={"Grain": 40.0},
        manager_per_unit=0.1, technician_per_unit=0.4, worker_per_unit=1.0,
        description="Livestock consume Grain feedstock",
    ),
    ProductionRecipe(
        role="Farmer", output="Food",
        inputs={"Grain": 1.0, "Produce": 1.0, "Fish": 1.0},
        manager_per_unit=0.1, technician_per_unit=0.4, worker_per_unit=1.0,
        description="Packaged balanced meals from Grain + Produce + Fish or Meat",
    ),

    # ----- Miner -----------------------------------------------------------
    ProductionRecipe(
        role="Miner", output="Ore",
        inputs={"Oil": 0.5, "Freight": 0.5},
        manager_per_unit=0.1, technician_per_unit=0.5, worker_per_unit=1.0,
    ),
    ProductionRecipe(
        role="Miner", output="Oil",
        inputs={"Freight": 0.5},
        manager_per_unit=0.1, technician_per_unit=0.5, worker_per_unit=0.5,
    ),
    ProductionRecipe(
        role="Miner", output="Metal",
        inputs={"Ore": 1.0, "Oil": 0.5},
        manager_per_unit=0.1, technician_per_unit=0.5, worker_per_unit=1.0,
        description="Smelt Metal from Ore and Oil",
    ),

    # ----- Transporter -----------------------------------------------------
    ProductionRecipe(
        role="Transporter", output="Freight",
        inputs={"Oil": 0.5, "Food": 0.2},
        manager_per_unit=0.1, technician_per_unit=0.25, worker_per_unit=1.0,
    ),
    ProductionRecipe(
        role="Transporter", output="PassengerSeats",
        inputs={"Oil": 0.4, "Food": 0.25},
        manager_per_unit=0.1, technician_per_unit=0.25, worker_per_unit=1.0,
    ),

    # ----- Educator --------------------------------------------------------
    ProductionRecipe(
        role="Educator", output="Expertise",
        inputs={},
        manager_per_unit=1.0, technician_per_unit=0.5, worker_per_unit=0.5,
        description="1 Professor required per unit of Expertise",
    ),
    ProductionRecipe(
        role="Educator", output="Courses",
        inputs={"Expertise": 1.0},
        manager_per_unit=0.5, technician_per_unit=1.0, worker_per_unit=0.0,
        description="1 Instructor + 0.5 Professor per Course; consumes 1 Expertise",
    ),
    ProductionRecipe(
        role="Educator", output="Patents",
        inputs={"Reagents": 0.5, "Expertise": 0.25},
        manager_per_unit=2.0, technician_per_unit=1.0, worker_per_unit=0.0,
        description="2 Professors per Patent; consumes a small Expertise input",
    ),

    # ----- Banker ----------------------------------------------------------
    # Banker no longer "produces" a Finance commodity.  Income comes from
    # loan interest spread and insurance premiums.  The recipe below models
    # underwriting capacity for InsurancePolicies; loans are tracked
    # separately via the loan ledger (see models/loan.py).
    ProductionRecipe(
        role="Banker", output="InsurancePolicies",
        inputs={"Expertise": 0.5},
        manager_per_unit=1.0, technician_per_unit=0.5, worker_per_unit=0.0,
        money_per_unit=8.0,
        description="8 Dp hedge cost per InsurancePolicy",
    ),

    # ----- Manufacturer ----------------------------------------------------
    # Manufacturer recipes are role-driven via MANUFACTURER_PRODUCT_LINES, but
    # we also expose canonical recipes for the product lines so the capacity
    # model can reason about them uniformly.
    ProductionRecipe(
        role="Manufacturer", output="FarmMachinery",
        inputs={"Metal": 2.0, "Oil": 1.0, "Freight": 2.0},
        manager_per_unit=0.1, technician_per_unit=1.0, worker_per_unit=1.5,
    ),
    ProductionRecipe(
        role="Manufacturer", output="Goods",
        inputs={"Metal": 1.0, "Oil": 1.0, "Freight": 1.0},
        manager_per_unit=0.1, technician_per_unit=1.0, worker_per_unit=1.0,
    ),
    ProductionRecipe(
        role="Manufacturer", output="MiningEquipment",
        inputs={"Metal": 3.0, "Oil": 2.0, "Freight": 3.0},
        manager_per_unit=0.2, technician_per_unit=1.5, worker_per_unit=1.0,
    ),
    ProductionRecipe(
        role="Manufacturer", output="MedicalDevices",
        inputs={"Metal": 1.0, "Oil": 1.0, "Freight": 1.0},
        manager_per_unit=0.2, technician_per_unit=1.5, worker_per_unit=0.5,
    ),
    ProductionRecipe(
        role="Manufacturer", output="TransportEquipment",
        inputs={"Metal": 2.0, "Oil": 2.0},
        manager_per_unit=0.1, technician_per_unit=1.0, worker_per_unit=1.5,
    ),
    ProductionRecipe(
        role="Manufacturer", output="Spares",
        inputs={"Metal": 2.0, "Oil": 1.0},
        manager_per_unit=0.1, technician_per_unit=0.5, worker_per_unit=0.5,
    ),

    # ----- Doctor (Medical Sciences) --------------------------------------
    # Reagents (formerly the Manufacturer's "LaboratoryEquipment") are now made
    # here from Oil + Ore — used in-house for MedicalSupplies/Vaccine and sold
    # to the Educator (2026-06-02).
    ProductionRecipe(
        role="Doctor", output="Reagents",
        inputs={"Oil": 1.0, "Ore": 1.0},
        manager_per_unit=0.2, technician_per_unit=1.0, worker_per_unit=0.5,
    ),
    ProductionRecipe(
        role="Doctor", output="MedicalSupplies",
        inputs={"Expertise": 0.25, "Reagents": 0.25},
        manager_per_unit=0.5, technician_per_unit=1.0, worker_per_unit=0.5,
    ),
    # Lab Tests (#26).  The spec's draft recipe named "LaboratoryEquipment",
    # renamed to Reagents in the 2026-06-02 pass — same input, new name.
    # Technician-heavy: an Orderly runs the samples, a Doctor signs them off.
    ProductionRecipe(
        role="Doctor", output="LaboratoryTests",
        inputs={"Expertise": 0.25, "Reagents": 0.2},
        manager_per_unit=0.25, technician_per_unit=0.5, worker_per_unit=0.0,
    ),
    ProductionRecipe(
        role="Doctor", output="Vaccine",
        inputs={"Expertise": 0.5, "Reagents": 1.0},
        manager_per_unit=1.0, technician_per_unit=0.0, worker_per_unit=0.0,
    ),
]


# Mandatory minimum default investment per role.
# Pre-selected in the Investing Phase; player may override but the screen
# warns if they deselect items leaving them unable to produce any output.
MANDATORY_MINIMUM_INVESTMENT: dict[str, list[str]] = {
    "Farmer":       ["farmer.tractor", "farmer.fishing_boat"],
    "Miner":        ["miner.excavator", "miner.crusher", "miner.oil_rig"],
    "Transporter":  ["transporter.cargo_ship", "transporter.passenger_liner"],
    "Educator":     ["educator.lecture_hall", "educator.library", "educator.technical_workshop"],
    "Banker":       ["banker.vault", "banker.underwriting_desk"],
    "Manufacturer": ["manufacturer.foundry", "manufacturer.assembly_line", "manufacturer.shipyard"],
    "Doctor":       ["doctor.hospital_ward", "doctor.vaccine_lab", "doctor.pathology_lab"],
}


def _multiply_capital_capacity(
    catalogue: list[CapitalItem], multiplier: int
) -> list[CapitalItem]:
    scaled: list[CapitalItem] = []
    for item in catalogue:
        effects = dict(item.effects)
        capacity = effects.get("capacity")
        if capacity:
            effects["capacity"] = {
                output: amount * multiplier
                for output, amount in capacity.items()
            }
            description = ", ".join(
                f"+{amount * multiplier:g} {output} capacity"
                for output, amount in capacity.items()
            )
        else:
            description = item.description
        scaled.append(CapitalItem(
            item_id=item.item_id,
            name=item.name,
            role=item.role,
            cost=item.cost,
            delivery_seasons=item.delivery_seasons,
            effects=effects,
            description=description,
            service_life_seasons=item.service_life_seasons,
            maintenance_per_season=item.maintenance_per_season,
            capacity_units=item.capacity_units,
            energy_intensive=item.energy_intensive,
            lease_terms=dict(item.lease_terms) if item.lease_terms else None,
        ))
    return scaled


def _multiply_recipe_productivity(
    recipes: list[ProductionRecipe], multiplier: int
) -> list[ProductionRecipe]:
    scaled: list[ProductionRecipe] = []
    for recipe in recipes:
        scaled.append(ProductionRecipe(
            role=recipe.role,
            output=recipe.output,
            inputs={
                resource: amount / multiplier
                for resource, amount in recipe.inputs.items()
            },
            manager_per_unit=recipe.manager_per_unit / multiplier,
            technician_per_unit=recipe.technician_per_unit / multiplier,
            worker_per_unit=recipe.worker_per_unit / multiplier,
            money_per_unit=recipe.money_per_unit / multiplier,
            description=recipe.description,
        ))
    return scaled


CAPITAL_CATALOGUE = _multiply_capital_capacity(
    CAPITAL_CATALOGUE, CAPACITY_PRODUCTIVITY_MULTIPLIER
)
PRODUCTION_RECIPES = _multiply_recipe_productivity(
    PRODUCTION_RECIPES, CAPACITY_PRODUCTIVITY_MULTIPLIER
)
