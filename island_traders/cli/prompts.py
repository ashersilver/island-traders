from __future__ import annotations
from ..models.resource import ResourceType
from ..engine.turn import TurnAction
from ..constants import CURRENCY_SYMBOL
# Re-export the cancel signals so existing callers continue to import them
# from this module.
from .signals import CANCEL_SENTINEL, ActionCancelled  # noqa: F401


# Player-facing labels for TurnAction values where the default title-cased
# rendering (`"purchase_capital".replace("_"," ").title()` = "Purchase
# Capital") isn't the wording we want.  Internal enum names + values stay
# unchanged — only the player-visible label changes.
ACTION_LABEL_OVERRIDES: dict[str, str] = {
    "purchase_capital": "Purchase Equipment",   # was "Purchase Capital" (2026-05-15 playtest)
}


def action_label(action: TurnAction) -> str:
    """Display label for a TurnAction in any IO adapter's action menu."""
    if action.value in ACTION_LABEL_OVERRIDES:
        return ACTION_LABEL_OVERRIDES[action.value]
    return action.value.replace("_", " ").title()


class IOAdapter:
    """All terminal I/O goes through this class. Subclass for tests or alternative UIs."""

    def print(self, text: str) -> None:
        print(text)

    def input(self, prompt: str) -> str:
        return input(prompt)

    def choose_action(self, player, available: list[TurnAction]) -> TurnAction:
        self.print(f"\n  {player.name}'s turn ({player.role_names()}) — choose:")
        for i, action in enumerate(available, 1):
            self.print(f"    {i}. {action_label(action)}")
        while True:
            raw = self.input("  > ").strip()
            if raw.isdigit():
                idx = int(raw) - 1
                if 0 <= idx < len(available):
                    return available[idx]
            self.print("  Invalid choice, try again.")

    def choose_resource(self, prompt: str, available: list[ResourceType]) -> ResourceType:
        self.print(f"\n  {prompt}")
        for i, r in enumerate(available, 1):
            self.print(f"    {i}. {r.value}")
        while True:
            raw = self.input("  > ").strip()
            if raw.isdigit():
                idx = int(raw) - 1
                if 0 <= idx < len(available):
                    return available[idx]
            self.print("  Invalid choice.")

    def choose_quantity(self, prompt: str, min_qty: int, max_qty: int) -> int:
        self.print(f"\n  {prompt} [{min_qty}–{max_qty}]")
        while True:
            raw = self.input("  > ").strip()
            if raw.isdigit():
                qty = int(raw)
                if min_qty <= qty <= max_qty:
                    return qty
            self.print(f"  Enter a number between {min_qty} and {max_qty}.")

    def choose_player(self, prompt: str, players: list) -> object:
        self.print(f"\n  {prompt}")
        for i, p in enumerate(players, 1):
            self.print(f"    {i}. {p.name} ({p.role_names()})")
        while True:
            raw = self.input("  > ").strip()
            if raw.isdigit():
                idx = int(raw) - 1
                if 0 <= idx < len(players):
                    return players[idx]
            self.print("  Invalid choice.")

    def confirm(self, prompt: str) -> bool:
        while True:
            raw = self.input(f"  {prompt} [y/n] > ").strip().lower()
            if raw in ("y", "yes"):
                return True
            if raw in ("n", "no"):
                return False
            self.print("  Enter y or n.")

    def choose_profession(self, prompt: str, available: list[str]) -> str:
        self.print(f"\n  {prompt}")
        for i, prof in enumerate(available, 1):
            self.print(f"    {i}. {prof}")
        while True:
            raw = self.input("  > ").strip()
            if raw.isdigit():
                idx = int(raw) - 1
                if 0 <= idx < len(available):
                    return available[idx]
            self.print("  Invalid choice.")

    def choose_option(self, prompt: str, options: list[dict]) -> object:
        """Choose from a list of labelled options.

        `options` is `[{"value": <any json-serialisable>, "label": str}, ...]`.
        Returns the chosen option's `value`.  Unlike `choose_quantity`, this
        presents named choices rather than a free numeric input — used for
        product selection so the player picks "Farm Machinery", not "3".
        """
        self.print(f"\n  {prompt}")
        for i, opt in enumerate(options, 1):
            self.print(f"    {i}. {opt['label']}")
        while True:
            raw = self.input("  > ").strip()
            if raw.isdigit():
                idx = int(raw) - 1
                if 0 <= idx < len(options):
                    return options[idx]["value"]
            self.print("  Invalid choice.")

    def ask_dollop_amount(self, prompt: str, max_dollops: float,
                          prefill: float = 0.0) -> float:
        sym = CURRENCY_SYMBOL
        hint = f" (max {max_dollops:.1f} {sym}, 0 to skip"
        if prefill:
            hint += f", suggested {prefill:.2f}"
        hint += ")"
        self.print(f"\n  {prompt}{hint}")
        while True:
            raw = self.input("  > ").strip()
            if raw == "" and prefill:
                return prefill
            try:
                val = float(raw)
                if -max_dollops <= val <= max_dollops:
                    return val
            except ValueError:
                pass
            self.print(f"  Enter a number between {-max_dollops:.1f} and {max_dollops:.1f}.")

    def ask_text(self, prompt: str, default: str = "") -> str:
        suffix = f" [{default}]" if default else ""
        raw = self.input(f"  {prompt}{suffix} > ").strip()
        return raw or default


class FakeIOAdapter(IOAdapter):
    """
    Scripted IO adapter for tests.
    Feed a list of responses; they are consumed in order.
    """

    def __init__(self, responses: list[str] | None = None):
        self._responses = list(responses or [])
        self.printed: list[str] = []

    def print(self, text: str) -> None:
        self.printed.append(text)

    def input(self, prompt: str) -> str:
        if self._responses:
            return self._responses.pop(0)
        return ""

    def choose_action(self, player, available: list[TurnAction]) -> TurnAction:
        return TurnAction.END_TURN

    def choose_resource(self, prompt, available):
        return available[0] if available else None

    def choose_quantity(self, prompt, min_qty, max_qty):
        return min_qty

    def choose_player(self, prompt, players):
        return players[0] if players else None

    def choose_profession(self, prompt, available):
        return available[0] if available else None

    def choose_option(self, prompt, options):
        return options[0]["value"] if options else None

    def confirm(self, prompt):
        return True

    def ask_dollop_amount(self, prompt, max_dollops, prefill=0.0):
        return 0.0

    def ask_text(self, prompt, default=""):
        if self._responses:
            return self._responses.pop(0)
        return default
