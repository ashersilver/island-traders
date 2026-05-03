from __future__ import annotations
from dataclasses import dataclass, field
from .role import Role
from .player import Player


@dataclass
class RoleAssignment:
    player: Player
    # Free-text agreements between players, e.g. "handles buying inputs"
    sub_responsibilities: list[str] = field(default_factory=list)


@dataclass
class RoleTeam:
    """Multiple players sharing a single role by mutual agreement."""
    role: Role
    assignments: list[RoleAssignment] = field(default_factory=list)
    # Index into assignments; rotates each season
    _active_index: int = 0

    def add_member(self, player: Player, responsibilities: list[str] | None = None) -> None:
        self.assignments.append(RoleAssignment(player, responsibilities or []))

    def active_player_for_production(self) -> Player:
        if not self.assignments:
            raise ValueError(f"RoleTeam for {self.role.name} has no members")
        return self.assignments[self._active_index % len(self.assignments)].player

    def rotate_active(self) -> None:
        self._active_index = (_active_index := self._active_index + 1) % max(len(self.assignments), 1)

    def describe_split(self) -> str:
        lines = [f"Role: {self.role.name} ({self.role.island})"]
        for a in self.assignments:
            resp = "; ".join(a.sub_responsibilities) or "general duties"
            lines.append(f"  {a.player.name}: {resp}")
        return "\n".join(lines)

    def all_players(self) -> list[Player]:
        return [a.player for a in self.assignments]
