from __future__ import annotations

from island_traders.constants import SEASONS
from island_traders.constants_capacity import CAPITAL_CATALOGUE
from island_traders.engine.engineering import effective_capital_service_life
from island_traders.engine.production import ProductionEngine
from island_traders.engine.turn import TurnManager
from island_traders.models.market import Market
from island_traders.models.player import Player
from island_traders.models.profession import EngineerSpecialty, Profession
from island_traders.models.resource import ResourceType
from island_traders.models.role import ROLES
from island_traders.models.training import (
    TrainingRegistry,
    away_seasons,
    engineer_training_duration,
)
from island_traders.server.app import GameManager


def _manager(training: TrainingRegistry, players: list[Player]) -> TurnManager:
    return TurnManager(
        players=players,
        production_engine=ProductionEngine(),
        trading_engine=None,
        market=Market(),
        io_adapter=None,
        training=training,
    )


def _educator(reagents: int = 20) -> Player:
    educator = Player(1, "Educator", [ROLES["Educator"]], 500.0)
    educator.receive_resources(ResourceType.COURSES, 10)
    educator.receive_resources(ResourceType.EXPERTISE, 20)
    educator.receive_resources(ResourceType.REAGENTS, reagents)
    educator.workforce.add_workers(2, training_level=1, profession=Profession.PROFESSOR.value)
    educator.workforce.add_workers(2, training_level=1, profession=Profession.LECTURER.value)
    return educator


def _manufacturer() -> Player:
    player = Player(0, "Maker", [ROLES["Manufacturer"]], 500.0)
    player.capital_inventory = {
        "manufacturer.foundry": 1,
        "manufacturer.assembly_line": 1,
    }
    player.receive_resources(ResourceType.METAL, 100)
    player.receive_resources(ResourceType.OIL, 100)
    player.receive_resources(ResourceType.FREIGHT, 100)
    player.workforce.add_workers(4, training_level=1, profession=Profession.ENGINEER.value)
    player.workforce.add_workers(4, training_level=1, profession=Profession.TRADESMAN.value)
    player.workforce.add_workers(8, training_level=0, profession=Profession.UNSKILLED.value)
    return player


def _capacity_output(player: Player, output: ResourceType) -> dict:
    cap = GameManager()._player_capacity(player)
    return next(row for row in cap["outputs"] if row["output"] == output.value)


def test_engineer_base_and_specialty_durations():
    assert away_seasons(Profession.ENGINEER.value) == 3
    assert engineer_training_duration(EngineerSpecialty.CHEMICAL.value) == 4
    assert engineer_training_duration(
        EngineerSpecialty.CHEMICAL.value,
        returning_engineer=True,
    ) == 1


def test_engineer_training_consumes_reagents_per_away_season():
    requester = Player(0, "Requester", [ROLES["Manufacturer"]], 500.0)
    worker = requester.workforce.add_workers(1)[0]
    educator = _educator(reagents=3)
    training = TrainingRegistry()
    req = training.propose(
        requester_id=requester.player_id,
        worker_ids=[worker.worker_id],
        educator_id=educator.player_id,
        dollops_to_educator=0.0,
        target_profession=Profession.ENGINEER.value,
        year=0,
        season=0,
        duration_seasons=away_seasons(Profession.ENGINEER.value),
    )
    manager = _manager(training, [requester, educator])

    ok, reason = manager._training_capacity_status(educator, req, year=0, season=0)
    assert ok, reason
    before = educator.inventory.get(ResourceType.REAGENTS)
    manager._consume_training_capacity(educator, req, year=0, season=0)
    assert educator.inventory.get(ResourceType.REAGENTS) == before - 3


def test_engineer_specialty_is_recorded_on_return():
    requester = Player(0, "Requester", [ROLES["Manufacturer"]], 500.0)
    worker = requester.workforce.add_workers(1)[0]
    educator = _educator()
    training = TrainingRegistry()
    req = training.propose(
        requester_id=requester.player_id,
        worker_ids=[worker.worker_id],
        educator_id=educator.player_id,
        dollops_to_educator=0.0,
        target_profession=Profession.ENGINEER.value,
        year=0,
        season=0,
        engineer_specialty=EngineerSpecialty.CHEMICAL.value,
        duration_seasons=4,
    )
    training.educator_approve(req.batch_id)
    training.dispatch(req.batch_id, year=0, season=0, num_seasons=len(SEASONS))
    requester.workforce.dispatch_for_training(req.worker_ids)

    due = training.process_returns(year=1, season=0)[0]
    returned = requester.workforce.return_from_training(
        due.worker_ids,
        due.target_profession,
        due.engineer_specialty,
    )

    assert returned[0].profession == Profession.ENGINEER.value
    assert returned[0].engineer_specialty == EngineerSpecialty.CHEMICAL.value
    assert returned[0].tier_name == "Engineer (Chemical)"


def test_industrial_engineer_adds_capacity_and_stacks_at_two():
    base = _manufacturer()
    industrial = _manufacturer()
    industrial.workforce.add_workers(
        3,
        training_level=1,
        profession=Profession.ENGINEER.value,
        engineer_specialty=EngineerSpecialty.INDUSTRIAL.value,
    )

    base_output = _capacity_output(base, ResourceType.FARM_MACHINERY)
    industrial_output = _capacity_output(industrial, ResourceType.FARM_MACHINERY)

    assert industrial_output["equipment_cap"] == base_output["equipment_cap"] + 4
    assert industrial_output["engineer_specialties"]["counts"]["Industrial"] == 2


def test_mechanical_engineer_extends_capital_life_and_relieves_technicians():
    player = _manufacturer()
    before = _capacity_output(player, ResourceType.FARM_MACHINERY)
    player.workforce.add_workers(
        1,
        training_level=1,
        profession=Profession.ENGINEER.value,
        engineer_specialty=EngineerSpecialty.MECHANICAL.value,
    )
    after = _capacity_output(player, ResourceType.FARM_MACHINERY)
    item = next(i for i in CAPITAL_CATALOGUE if i.item_id == "manufacturer.foundry")

    assert effective_capital_service_life(player, item.service_life_seasons) == 25
    assert after["workforce_cap"] > before["workforce_cap"]


def test_electrical_engineer_boosts_production_efficiency():
    player = _manufacturer()
    engine = ProductionEngine()
    before = engine._labour_productivity_factor(player, "Spring")
    player.workforce.add_workers(
        2,
        training_level=1,
        profession=Profession.ENGINEER.value,
        engineer_specialty=EngineerSpecialty.ELECTRICAL.value,
    )
    after = engine._labour_productivity_factor(player, "Spring")

    assert after == min(1.0, before + 0.10)


def test_chemical_engineer_reduces_oil_inputs_and_adds_reagent_capacity():
    manufacturer = _manufacturer()
    manufacturer.receive_resources(ResourceType.METAL, 900)
    manufacturer.receive_resources(ResourceType.FREIGHT, 900)
    base_manufacturer = _capacity_output(manufacturer, ResourceType.FARM_MACHINERY)
    manufacturer.workforce.add_workers(
        1,
        training_level=1,
        profession=Profession.ENGINEER.value,
        engineer_specialty=EngineerSpecialty.CHEMICAL.value,
    )
    chemical_manufacturer = _capacity_output(manufacturer, ResourceType.FARM_MACHINERY)
    assert chemical_manufacturer["input_cap"] > base_manufacturer["input_cap"]

    doctor = Player(2, "Doctor", [ROLES["Doctor"]], 500.0)
    doctor.capital_inventory = {"doctor.reagent_lab": 1}
    doctor.receive_resources(ResourceType.OIL, 100)
    doctor.receive_resources(ResourceType.ORE, 100)
    doctor.workforce.add_workers(4, training_level=1, profession=Profession.DOCTOR.value)
    doctor.workforce.add_workers(4, training_level=1, profession=Profession.MEDICAL_TECHNICIAN.value)
    base_doctor_output = _capacity_output(doctor, ResourceType.REAGENTS)
    doctor.workforce.add_workers(
        1,
        training_level=1,
        profession=Profession.ENGINEER.value,
        engineer_specialty=EngineerSpecialty.CHEMICAL.value,
    )

    reagent_output = _capacity_output(doctor, ResourceType.REAGENTS)
    assert reagent_output["equipment_cap"] == base_doctor_output["equipment_cap"] + 2


def test_inactive_specialized_engineer_does_not_apply_effect():
    player = _manufacturer()
    engineer = player.workforce.add_workers(
        1,
        training_level=1,
        profession=Profession.ENGINEER.value,
        engineer_specialty=EngineerSpecialty.INDUSTRIAL.value,
    )[0]
    active = _capacity_output(player, ResourceType.FARM_MACHINERY)
    engineer.in_training = True
    inactive = _capacity_output(player, ResourceType.FARM_MACHINERY)

    assert active["equipment_cap"] == inactive["equipment_cap"] + 2
