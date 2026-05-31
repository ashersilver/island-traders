"""Workers must only depart for training once it is approved.

Playtest 2026-05-29: requesting training made the workers vanish from the
requester's island the instant they clicked "Request Training" — before any
approval. Root cause: an AI Educator approved AND dispatched inside the
*requester's* turn. They must instead stay home (producing) until the Educator
approves on the Educator's own turn.
"""
from __future__ import annotations

from island_traders.cli.prompts import FakeIOAdapter
from island_traders.engine.game import Game, GameConfig, PlayerSpec
from island_traders.engine.turn import TurnResult


class _AutoIO(FakeIOAdapter):
    def choose_profession(self, prompt, available):
        return available[0]

    def choose_quantity(self, prompt, mn, mx):
        return 1

    def choose_player(self, prompt, players):
        return players[0]

    def ask_dollop_amount(self, prompt, mx, prefill=0.0):
        return 50.0

    def confirm(self, prompt, request_summary=None):
        return True

    def choose_option(self, prompt, options, request_summary=None):
        return options[0]["value"]


def _game(educator_human: bool) -> Game:
    cfg = GameConfig(num_years=1, player_specs=[
        PlayerSpec(name="Farmer", role_names=["Farmer"], is_human=True),
        PlayerSpec(name="Educator", role_names=["Educator"], is_human=educator_human),
    ])
    g = Game(cfg, _AutoIO())
    g.setup()
    return g


def test_request_does_not_dispatch_workers_with_ai_educator():
    g = _game(educator_human=False)
    farmer, educator = g.players
    res = TurnResult(player_id=farmer.player_id, season="Spring", year=0)

    g.turn_manager._action_request_training(farmer, res, "Spring", 0)

    reqs = g.training.active_for_player(farmer.player_id)
    assert reqs, "a training request should have been created"
    # Workers stay home until approval — none in training yet.
    assert farmer.workforce.training_count == 0
    assert all(r.status.value == "awaiting_educator" for r in reqs)


def test_ai_educator_approves_and_dispatches_on_its_own_turn():
    g = _game(educator_human=False)
    farmer, educator = g.players
    res = TurnResult(player_id=farmer.player_id, season="Spring", year=0)
    g.turn_manager._action_request_training(farmer, res, "Spring", 0)
    assert farmer.workforce.training_count == 0

    # The AI Educator processes its queue on its OWN turn -> approve + dispatch.
    res2 = TurnResult(player_id=educator.player_id, season="Spring", year=0)
    g.turn_manager._ai_review_training_queue(educator, res2, "Spring", 0)

    assert farmer.workforce.training_count == 1
    reqs = g.training.active_for_player(farmer.player_id)
    assert any(r.status.value == "dispatched" for r in reqs)


def test_request_does_not_dispatch_workers_with_human_educator():
    g = _game(educator_human=True)
    farmer, educator = g.players
    res = TurnResult(player_id=farmer.player_id, season="Spring", year=0)

    g.turn_manager._action_request_training(farmer, res, "Spring", 0)

    assert farmer.workforce.training_count == 0
    reqs = g.training.active_for_player(farmer.player_id)
    assert all(r.status.value == "awaiting_educator" for r in reqs)
