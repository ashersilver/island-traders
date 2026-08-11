"""Transporter-operated storage contracts.

Unlike owned stores, rental space belongs to a Transporter and is allocated to
another island only while its contract remains active.  The ledger owns the
shared-capacity accounting; players ask it for their rented protection through
``Player.storage_capacity``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from threading import RLock

from .resource import ResourceType


class StorageContractStatus(Enum):
    ACTIVE = "active"
    CANCELLED = "cancelled"
    LAPSED = "lapsed"


@dataclass
class StorageContract:
    contract_id: int
    transporter_id: int
    renter_id: int
    item_id: str
    resource: str
    capacity: int
    fee_per_season: float
    started_year: int
    started_season: int
    status: StorageContractStatus = StorageContractStatus.ACTIVE
    payments_made: int = 0
    last_payment_year: int = -1
    last_payment_season: int = -1
    ended_year: int = -1
    ended_season: int = -1


@dataclass
class StorageContractLedger:
    contracts: list[StorageContract] = field(default_factory=list)
    _next_id: int = 0
    _players_by_id: dict[int, object] = field(default_factory=dict, repr=False)
    _capacity_lock: RLock = field(default_factory=RLock, repr=False)

    def bind_players(self, players: list[object]) -> None:
        """Attach live players so capacity reflects maintained warehouses."""
        self._players_by_id = {
            int(player.player_id): player for player in players
        }
        for player in players:
            player.bind_storage_contract_ledger(self)

    def active_contracts(self) -> list[StorageContract]:
        return [
            contract for contract in self.contracts
            if contract.status == StorageContractStatus.ACTIVE
        ]

    def active_for_player(self, player_id: int) -> list[StorageContract]:
        return [
            contract for contract in self.active_contracts()
            if contract.renter_id == player_id or contract.transporter_id == player_id
        ]

    def get(self, contract_id: int) -> StorageContract:
        for contract in self.contracts:
            if contract.contract_id == contract_id:
                return contract
        raise KeyError(f"No storage contract #{contract_id}")

    @staticmethod
    def _rental_spec(item_id: str) -> dict:
        from ..constants_capacity import CAPITAL_CATALOGUE
        from .capacity import find_item

        item = find_item(CAPITAL_CATALOGUE, item_id)
        spec = item.effects.get("storage_rental") if item else None
        if not isinstance(spec, dict):
            raise ValueError(f"{item_id} is not a Transporter storage warehouse.")
        return spec

    def _effective_capacity(self, transporter_id: int, item_id: str) -> int:
        transporter = self._players_by_id.get(transporter_id)
        if transporter is None:
            return 0
        spec = self._rental_spec(item_id)
        units = transporter.effective_capital_inventory().get(item_id, 0)
        return max(0, int(spec.get("capacity", 0))) * units

    def committed_capacity(self, transporter_id: int, item_id: str) -> int:
        return sum(
            contract.capacity for contract in self.active_contracts()
            if contract.transporter_id == transporter_id and contract.item_id == item_id
        )

    def free_capacity(self, transporter_id: int, item_id: str) -> int:
        return max(
            0,
            self._effective_capacity(transporter_id, item_id)
            - self.committed_capacity(transporter_id, item_id),
        )

    def effective_capacity_for_contract(self, contract: StorageContract) -> int:
        """Return live protection allocated to one contract.

        If a warehouse is temporarily unmaintained or failed, active contracts
        remain on the books but newest contracts lose capacity first.  That
        keeps the warehouse from protecting stock it cannot actually hold.
        """
        remaining = self._effective_capacity(
            contract.transporter_id, contract.item_id
        )
        for current in sorted(self.active_contracts(), key=lambda c: c.contract_id):
            if (
                current.transporter_id != contract.transporter_id
                or current.item_id != contract.item_id
            ):
                continue
            allocated = min(current.capacity, remaining)
            if current.contract_id == contract.contract_id:
                return allocated
            remaining -= allocated
            if remaining <= 0:
                return 0
        return 0

    def rented_capacity_for(
        self, renter_id: int, resource: ResourceType | str
    ) -> int:
        resource_name = resource.value if isinstance(resource, ResourceType) else str(resource)
        return sum(
            self.effective_capacity_for_contract(contract)
            for contract in self.active_contracts()
            if contract.renter_id == renter_id and contract.resource == resource_name
        )

    def create(
        self,
        *,
        transporter_id: int,
        renter_id: int,
        item_id: str,
        resource: ResourceType | str,
        capacity: int,
        year: int,
        season: int,
        fee_per_season: float | None = None,
    ) -> StorageContract:
        # Web turns can run concurrently; reservation check and append must be
        # one transaction or two renters could both see the same final slots.
        with self._capacity_lock:
            if transporter_id == renter_id:
                raise ValueError("A Transporter cannot rent warehouse space to itself.")
            transporter = self._players_by_id.get(transporter_id)
            renter = self._players_by_id.get(renter_id)
            if transporter is None or renter is None:
                raise ValueError("Both the Transporter and renter must be active islands.")
            if not any(role.name == "Transporter" for role in transporter.roles):
                raise ValueError("Storage capacity must be supplied by a Transporter island.")
            if capacity <= 0:
                raise ValueError("Storage capacity must be positive.")
            spec = self._rental_spec(item_id)
            resource_name = resource.value if isinstance(resource, ResourceType) else str(resource)
            if resource_name not in spec.get("resources", ()):
                allowed = ", ".join(spec.get("resources", ()))
                raise ValueError(f"{item_id} stores {allowed}, not {resource_name}.")
            if capacity > self.free_capacity(transporter_id, item_id):
                raise ValueError("That warehouse does not have enough free capacity.")
            fee_per_unit = float(spec.get("fee_per_unit", 0.0))
            calculated_fee = round(int(capacity) * fee_per_unit, 2)
            if fee_per_season is not None and round(float(fee_per_season), 2) != calculated_fee:
                raise ValueError("Storage contract fee must use the warehouse catalogue rate.")
            contract = StorageContract(
                contract_id=self._next_id,
                transporter_id=transporter_id,
                renter_id=renter_id,
                item_id=item_id,
                resource=resource_name,
                capacity=int(capacity),
                fee_per_season=calculated_fee,
                started_year=year,
                started_season=season,
            )
            self.contracts.append(contract)
            self._next_id += 1
            return contract

    def cancel(self, contract_id: int, year: int, season: int) -> StorageContract:
        contract = self.get(contract_id)
        if contract.status != StorageContractStatus.ACTIVE:
            raise ValueError("Storage contract is no longer active.")
        contract.status = StorageContractStatus.CANCELLED
        contract.ended_year, contract.ended_season = year, season
        return contract

    def lapse(self, contract_id: int, year: int, season: int) -> StorageContract:
        contract = self.get(contract_id)
        if contract.status == StorageContractStatus.ACTIVE:
            contract.status = StorageContractStatus.LAPSED
            contract.ended_year, contract.ended_season = year, season
        return contract

    def record_payment(self, contract_id: int, year: int, season: int) -> StorageContract:
        contract = self.get(contract_id)
        contract.payments_made += 1
        contract.last_payment_year, contract.last_payment_season = year, season
        return contract

    def due_contracts(self, year: int, season: int) -> list[StorageContract]:
        return [
            contract for contract in self.active_contracts()
            if (contract.started_year, contract.started_season) <= (year, season)
            and (contract.last_payment_year, contract.last_payment_season) != (year, season)
        ]

    def income_for_transporter(self, transporter_id: int, year: int, season: int) -> float:
        return round(sum(
            contract.fee_per_season for contract in self.contracts
            if contract.transporter_id == transporter_id
            and (contract.last_payment_year, contract.last_payment_season) == (year, season)
        ), 2)
