"""
Island Traders — interactive CLI session.

Usage:
    island-traders
    python -m island_traders.cli.session
"""
from __future__ import annotations
from pathlib import Path
from ..engine.game import Game, GameConfig, PlayerSpec
from ..cli.display import Display
from ..cli.prompts import IOAdapter
from ..models.role import ROLES

DEFAULT_SAVE_PATH = "island_traders_save.json"


def build_config_from_cli(io: IOAdapter) -> GameConfig:
    io.print("\n" + "=" * 50)
    io.print("  ISLAND TRADERS")
    io.print("  A resource trading board game")
    io.print("  Currency: Dollops (Dp)")
    io.print("=" * 50)

    # Number of years
    io.print("\nHow many years to play? (default 3)")
    raw = io.input("> ").strip()
    num_years = int(raw) if raw.isdigit() and int(raw) >= 1 else 3

    # Number of players
    io.print(f"\nHow many players? (2–{len(ROLES)})")
    while True:
        raw = io.input("> ").strip()
        if raw.isdigit() and 2 <= int(raw) <= len(ROLES):
            num_players = int(raw)
            break
        io.print(f"  Enter a number between 2 and {len(ROLES)}.")

    role_names = list(ROLES.keys())
    specs: list[PlayerSpec] = []

    for i in range(num_players):
        io.print(f"\n--- Player {i + 1} ---")
        name = io.input("  Name: ").strip() or f"Player{i + 1}"

        # Human or AI
        is_human = io.confirm("  Human player?")

        # Role selection
        available_roles = [r for r in role_names if not any(r in s.role_names for s in specs)]
        io.print("  Available roles:")
        for j, rname in enumerate(available_roles, 1):
            role = ROLES[rname]
            produces_str = ", ".join(r.value for r in role.produces) or "—"
            needs_str    = ", ".join(r.value for r in role.needs)    or "—"
            io.print(f"    {j}. {rname} — {role.island}")
            io.print(f"       Produces: {produces_str}   |   Needs: {needs_str}")

        chosen_roles: list[str] = []
        while True:
            raw = io.input(f"  Choose role (1–{len(available_roles)}, or 'done' if multi-role): ").strip()
            if raw == "done" and chosen_roles:
                break
            if raw.isdigit():
                idx = int(raw) - 1
                if 0 <= idx < len(available_roles):
                    rname = available_roles[idx]
                    if rname not in chosen_roles:
                        chosen_roles.append(rname)
                        io.print(f"  Added role: {rname}")
                    io.print("  Add another role? Type another number or 'done'.")
            if len(chosen_roles) == len(available_roles):
                break

        specs.append(PlayerSpec(name=name, role_names=chosen_roles, is_human=is_human))

    return GameConfig(player_specs=specs, num_years=num_years)


def _show_players(io: IOAdapter, game: Game) -> None:
    """Print the player roster after setup / after loading a save."""
    from ..constants import CURRENCY_SYMBOL, STARTING_PRODUCTION_CAPACITY
    sym = CURRENCY_SYMBOL
    io.print("\n" + "=" * 56)
    io.print("  ISLAND TRADERS — PLAYER ROSTER")
    io.print("=" * 56)
    for p in game.players:
        io.print(f"\n  {p.name}  ({'Human' if p.is_human else 'AI'})")
        for role in p.roles:
            produces_str = ", ".join(r.value for r in role.produces) or "—"
            needs_str    = ", ".join(r.value for r in role.needs)    or "—"
            io.print(f"    Role   : {role.name}")
            io.print(f"    Island : {role.island}")
            io.print(f"    Produces: {produces_str}")
            io.print(f"    Needs   : {needs_str}")
        ws = p.workforce.summary()
        io.print(
            f"    Starting Dollops : {p.dollops:.0f} {sym}\n"
            f"    Capacity         : {p.production_capacity*100:.0f}%\n"
            f"    Workforce        : {ws['total']} workers  "
            f"({ws['avg_efficiency_pct']}% avg efficiency)"
        )
    io.print("=" * 56)


def main() -> None:
    io = IOAdapter()
    save_path = DEFAULT_SAVE_PATH

    # Check for an existing save file
    game: Game | None = None
    if Path(save_path).exists():
        io.print(f"\n  Save file found: {save_path}")
        if io.confirm("  Resume previous game?"):
            try:
                game = Game.load(save_path, io)
                season_name = ["Spring", "Summer", "Autumn", "Winter"][game._resume_season]
                io.print(
                    f"\n  Resuming from Year {game._resume_year + 1}, {season_name}."
                )
                _show_players(io, game)
            except Exception as e:
                io.print(f"  Could not load save file: {e}")
                io.print("  Starting a new game instead.")
                game = None

    if game is None:
        config = build_config_from_cli(io)
        game = Game(config, io, save_path=save_path)
        game.setup()
        _show_players(io, game)

    summary = game.run()
    io.print(Display.game_summary(summary))


if __name__ == "__main__":
    main()
