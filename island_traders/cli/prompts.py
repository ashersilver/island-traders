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
    "lease_capital": "Lease Equipment",
    "pay_lease": "Pay Lease",
    "pay_rebuild_levy": "Pay Rebuild Levy",
    "reorder_training_queue": "Reorder Training Queue",
    "reject_training_request": "Reject Training Request",
    "counter_training_request": "Counter Training Request",
    "ack_training_decision": "Acknowledge Training Decision",
    "supply_training_expertise": "Supply Expertise to Educator",
    "request_medical_staff": "Request Medical Staff",
    "review_staffing_requests": "Review Staffing Requests",
    "repurpose_worker": "Repurpose Worker",
    "lend_to_island": "Lend Cash to Island",
    "repay_shareholder_loan": "Repay Shareholder Loan",
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
        self.print(f"\n  {player.name} ({player.role_names()}) — choose an action:")
        for i, action in enumerate(available, 1):
            self.print(f"    {i}. {action_label(action)}")
        while True:
            raw = self.input("  > ").strip()
            if raw.isdigit():
                idx = int(raw) - 1
                if 0 <= idx < len(available):
                    return available[idx]
            self.print("  Invalid choice, try again.")

    def set_produce_options(self, player_id, options: list[dict]) -> None:
        """Hook: dashboard adapters cache per-product Produce buttons.

        No-op for the terminal adapter, which keeps the single Produce action
        plus a follow-up product picker (see TurnManager._action_produce).
        """
        return None

    def take_produce_choice(self, player_id):
        """Hook: return (and clear) a pre-selected produce option key, or None.

        The dashboard adapter records which "Produce <product>" button the
        player clicked so _action_produce can skip the product picker.  Base
        adapter always returns None → the picker path runs.
        """
        return None

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

    def choose_quantity(
        self, prompt: str, min_qty: int, max_qty: int, default: int | None = None
    ) -> int:
        hint = f"[{min_qty}–{max_qty}]"
        if default is not None:
            hint += f" (Enter for {default})"
        self.print(f"\n  {prompt} {hint}")
        while True:
            raw = self.input("  > ").strip()
            if not raw and default is not None:
                return max(min_qty, min(default, max_qty))
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

    def confirm(self, prompt: str, request_summary: dict | None = None) -> bool:
        if request_summary:
            self.print(self._format_request_summary(request_summary))
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

    def choose_option(
        self, prompt: str, options: list[dict], request_summary: dict | None = None
    ) -> object:
        """Choose from a list of labelled options.

        `options` is `[{"value": <any json-serialisable>, "label": str}, ...]`.
        Returns the chosen option's `value`.  Unlike `choose_quantity`, this
        presents named choices rather than a free numeric input — used for
        product selection so the player picks "Farm Machinery", not "3".
        """
        if request_summary:
            self.print(self._format_request_summary(request_summary))
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

    def _format_request_summary(self, summary: dict) -> str:
        lines = [summary.get("title", "Training request")]
        for label, value in summary.get("fields", []):
            lines.append(f"  - {label:<18} {value}")
        return "\n".join(lines)

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

    def choose_quantity(self, prompt, min_qty, max_qty, default=None):
        return min_qty

    def choose_player(self, prompt, players):
        return players[0] if players else None

    def choose_profession(self, prompt, available):
        return available[0] if available else None

    def choose_option(self, prompt, options, request_summary=None):
        return options[0]["value"] if options else None

    def confirm(self, prompt, request_summary=None):
        return True

    def ask_dollop_amount(self, prompt, max_dollops, prefill=0.0):
        return 0.0

    def ask_text(self, prompt, default=""):
        if self._responses:
            return self._responses.pop(0)
        return default
