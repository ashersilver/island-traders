"""Tests for Issue #6 (loan rollover) and Issue #5 (insurance review/cancel).

Covers:
  * `LoanLedger.rollover_loan` semantics — old loan ROLLED_OVER, new loan
    inherits the old loan's repayment_amount as its principal.
  * `_action_rollover_loan` end-to-end via a scripted IO adapter.
  * Borrower-side filtering: external funding loans (lender_id == -1) and
    lender-side loans are not eligible for rollover.
  * `InsurancePolicy.cancel_refund` pro-rata math + zero-cases.
  * `Player.cancel_insurance_policy` deactivates the policy and returns refund.
  * `_action_manage_insurance` end-to-end with Banker debit + holder credit.
"""
from __future__ import annotations

from island_traders.cli.prompts import FakeIOAdapter
from island_traders.engine.production import ProductionEngine
from island_traders.engine.trading import TradingEngine
from island_traders.engine.turn import TurnManager, TurnResult
from island_traders.models.deal import DealLedger
from island_traders.models.insurance import InsurancePolicy
from island_traders.models.loan import LoanLedger, LoanStatus
from island_traders.models.market import Market
from island_traders.models.player import Player
from island_traders.models.role import ROLES


# ---------------------------------------------------------------------------
# Test IO adapter that scripts answers for chained prompts
# ---------------------------------------------------------------------------
class ScriptedIO(FakeIOAdapter):
    def __init__(
        self,
        *,
        quantities: list[int] | None = None,
        amounts: list[float] | None = None,
        confirms: list[bool] | None = None,
    ):
        super().__init__()
        self.quantities = list(quantities or [])
        self.amounts = list(amounts or [])
        self.confirms = list(confirms or [])

    def choose_quantity(self, prompt, min_qty, max_qty):
        if self.quantities:
            return self.quantities.pop(0)
        return min_qty

    def ask_dollop_amount(self, prompt, max_dollops):
        if self.amounts:
            return self.amounts.pop(0)
        return 0.0

    def confirm(self, prompt):
        if self.confirms:
            return self.confirms.pop(0)
        return True


def _turn_manager(players, loan_ledger, io):
    market = Market()
    return TurnManager(
        players=players,
        production_engine=ProductionEngine(),
        trading_engine=TradingEngine(market, DealLedger()),
        market=market,
        io_adapter=io,
        loan_ledger=loan_ledger,
    )


# ===========================================================================
# Loan rollover — ledger primitives
# ===========================================================================

def test_rollover_marks_old_loan_as_rolled_over_and_creates_new_loan():
    ledger = LoanLedger()
    old = ledger.create_loan(
        borrower_id=1, lender_id=0, principal=100.0, interest_rate=0.10,
        issued_year=0, issued_season=0, term_years=1,
    )
    assert old.repayment_amount == 110.0  # 100 * 1.10

    new = ledger.rollover_loan(
        loan_id=old.loan_id,
        new_rate=0.12,
        new_term_years=2,
        year=0,
        season=2,
    )
    assert old.status == LoanStatus.ROLLED_OVER
    assert new.principal == 110.0  # = old.repayment_amount
    assert new.interest_rate == 0.12
    assert new.term_years == 2
    assert new.issued_year == 0
    assert new.issued_season == 2
    assert new.maturity_year == 2  # 0 + 2
    assert new.rolled_over_from_loan_id == old.loan_id
    # Old loan no longer counted as outstanding
    assert ledger.outstanding_debt(1) == new.repayment_amount


def test_rollover_rejects_unknown_loan():
    ledger = LoanLedger()
    import pytest
    with pytest.raises(ValueError, match="No loan with id"):
        ledger.rollover_loan(loan_id=999, new_rate=0.10,
                             new_term_years=1, year=0, season=0)


def test_rollover_rejects_inactive_loan():
    ledger = LoanLedger()
    loan = ledger.create_loan(
        borrower_id=1, lender_id=0, principal=100.0, interest_rate=0.10,
        issued_year=0, issued_season=0, term_years=1,
    )
    loan.status = LoanStatus.REPAID
    import pytest
    with pytest.raises(ValueError, match="cannot roll over"):
        ledger.rollover_loan(loan_id=loan.loan_id, new_rate=0.10,
                             new_term_years=1, year=0, season=0)


def test_rollover_rejects_invalid_term():
    ledger = LoanLedger()
    loan = ledger.create_loan(
        borrower_id=1, lender_id=0, principal=100.0, interest_rate=0.10,
        issued_year=0, issued_season=0, term_years=1,
    )
    import pytest
    with pytest.raises(ValueError, match="must be 1-3"):
        ledger.rollover_loan(loan_id=loan.loan_id, new_rate=0.10,
                             new_term_years=4, year=0, season=0)


# ===========================================================================
# Loan rollover — action-level end-to-end
# ===========================================================================

def test_action_rollover_picks_loan_and_creates_new_at_quoted_rate():
    borrower = Player(player_id=1, name="Farmer", roles=[ROLES["Farmer"]],
                      dollops=50.0, is_human=True)
    banker = Player(player_id=0, name="Banker", roles=[ROLES["Banker"]],
                    dollops=0.0, is_human=True)
    ledger = LoanLedger()
    old = ledger.create_loan(
        borrower_id=borrower.player_id, lender_id=banker.player_id,
        principal=100.0, interest_rate=0.10,
        issued_year=0, issued_season=0, term_years=1,
    )

    # Loan picker now uses choose_option (named labels per #21 pattern,
    # 2026-05-27); FakeIOAdapter.choose_option defaults to options[0]
    # which is the only loan available here.  Only the new-term prompt
    # consumes from `quantities`.
    io = ScriptedIO(quantities=[2], confirms=[True])
    tm = _turn_manager([banker, borrower], ledger, io)
    result = TurnResult(player_id=borrower.player_id, season=2, year=0)

    tm._action_rollover_loan(borrower, result, year=0, season_index=2)

    all_loans = ledger.all_loans()
    assert len(all_loans) == 2
    assert all_loans[0].status == LoanStatus.ROLLED_OVER
    new_loan = all_loans[1]
    assert new_loan.borrower_id == borrower.player_id
    assert new_loan.lender_id == banker.player_id
    assert new_loan.principal == old.repayment_amount  # 110
    assert new_loan.term_years == 2
    assert new_loan.rolled_over_from_loan_id == old.loan_id
    # Borrower cash unchanged — no money moves at rollover
    assert borrower.dollops == 50.0
    assert any("rollover" in a for a in result.actions_taken)


def test_action_rollover_returns_when_no_active_loans():
    borrower = Player(player_id=1, name="Farmer", roles=[ROLES["Farmer"]],
                      dollops=50.0, is_human=True)
    ledger = LoanLedger()
    io = ScriptedIO()
    tm = _turn_manager([borrower], ledger, io)
    result = TurnResult(player_id=borrower.player_id, season=0, year=0)

    tm._action_rollover_loan(borrower, result, year=0, season_index=0)
    assert result.actions_taken == []
    assert ledger.all_loans() == []


def test_action_rollover_excludes_external_bank_funding_loans():
    """A funding loan (lender_id == -1) is the Bank borrowing externally —
    individual borrowers can't roll those over from a player action."""
    banker = Player(player_id=0, name="Banker", roles=[ROLES["Banker"]],
                    dollops=0.0, is_human=True)
    ledger = LoanLedger()
    # External funding loan to the bank
    ledger.create_loan(
        borrower_id=banker.player_id, lender_id=-1, principal=100.0,
        interest_rate=0.05, issued_year=0, issued_season=0, term_years=1,
    )
    io = ScriptedIO()
    tm = _turn_manager([banker], ledger, io)
    result = TurnResult(player_id=banker.player_id, season=0, year=0)
    tm._action_rollover_loan(banker, result, year=0, season_index=0)
    # No rollover happened — the only loan was filtered out as external
    assert ledger.all_loans()[0].status == LoanStatus.ACTIVE
    assert result.actions_taken == []


def test_action_rollover_cancels_on_confirm_no():
    borrower = Player(player_id=1, name="Farmer", roles=[ROLES["Farmer"]],
                      dollops=50.0, is_human=True)
    banker = Player(player_id=0, name="Banker", roles=[ROLES["Banker"]],
                    dollops=0.0, is_human=True)
    ledger = LoanLedger()
    ledger.create_loan(
        borrower_id=borrower.player_id, lender_id=banker.player_id,
        principal=100.0, interest_rate=0.10,
        issued_year=0, issued_season=0, term_years=1,
    )
    # Loan picker is now choose_option (FakeIOAdapter returns first
    # option = the only loan); only the new-term prompt consumes from
    # `quantities`.  Confirm=False cancels the rollover.
    io = ScriptedIO(quantities=[1], confirms=[False])
    tm = _turn_manager([banker, borrower], ledger, io)
    result = TurnResult(player_id=borrower.player_id, season=2, year=0)
    tm._action_rollover_loan(borrower, result, year=0, season_index=2)
    assert ledger.all_loans()[0].status == LoanStatus.ACTIVE  # unchanged
    assert result.actions_taken == []


def test_action_rollover_uses_named_option_picker_not_numeric_index():
    """Regression for 2026-05-27 playtest ask on #6: the loan picker
    must present loans as named choose_option entries (labels include
    principal / rate / maturity), not a 'type a number' choose_quantity
    against a separate text list.  Matches the lease/invest/purchase
    pattern (Issue #21)."""
    borrower = Player(player_id=1, name="Farmer", roles=[ROLES["Farmer"]],
                      dollops=50.0, is_human=True)
    banker = Player(player_id=0, name="Banker", roles=[ROLES["Banker"]],
                    dollops=0.0, is_human=True)
    ledger = LoanLedger()
    ledger.create_loan(
        borrower_id=borrower.player_id, lender_id=banker.player_id,
        principal=100.0, interest_rate=0.10,
        issued_year=0, issued_season=0, term_years=1,
    )
    ledger.create_loan(
        borrower_id=borrower.player_id, lender_id=banker.player_id,
        principal=200.0, interest_rate=0.08,
        issued_year=0, issued_season=0, term_years=2,
    )

    captured: dict = {}

    class CapturingIO(ScriptedIO):
        def choose_option(self, prompt, options, request_summary=None):
            captured["prompt"] = prompt
            captured["options"] = options
            # Pick the second loan by its loan_id so the test exercises
            # the str-to-int conversion path too.
            return options[1]["value"]

        def choose_quantity(self, prompt, min_qty, max_qty):
            captured.setdefault("quantity_prompts", []).append(prompt)
            return super().choose_quantity(prompt, min_qty, max_qty)

    io = CapturingIO(quantities=[2], confirms=[True])
    tm = _turn_manager([banker, borrower], ledger, io)
    result = TurnResult(player_id=borrower.player_id, season=0, year=0)
    tm._action_rollover_loan(borrower, result, year=0, season_index=0)

    # Named-option picker was used.
    assert "options" in captured, "Rollover did not call choose_option"
    assert captured["prompt"] == "Roll over which loan?"
    assert all("value" in o and "label" in o for o in captured["options"])
    # Labels carry the loan's principal + rate context.
    assert any("100.0" in o["label"] for o in captured["options"])
    assert any("200.0" in o["label"] for o in captured["options"])
    # The new loan picked up the second loan's repayment_amount.
    new_loan = ledger.all_loans()[2]
    assert new_loan.principal == ledger.all_loans()[1].repayment_amount
    # And choose_quantity was used ONLY for the new-term prompt, not
    # for the loan pick.
    quantity_prompts = captured.get("quantity_prompts", [])
    assert not any("which loan" in p.lower() for p in quantity_prompts)


# ===========================================================================
# Insurance — model + ledger
# ===========================================================================

def _policy(*, premium=40.0, purchased_tick=0, expires_at_tick=4, policy_id=1):
    return InsurancePolicy(
        policy_id=policy_id,
        policy_type="life",
        holder_player_id=1,
        banker_player_id=0,
        premium_paid=premium,
        purchased_tick=purchased_tick,
        expires_at_tick=expires_at_tick,
    )


def test_cancel_refund_pro_rata():
    """4-season policy paid 40 Dp.  After 0 seasons → full 40, after 1 → 30,
    after 2 → 20, after 4 (expired) → 0."""
    p = _policy()
    assert p.cancel_refund(year=0, season_index=0) == 40.0
    assert p.cancel_refund(year=0, season_index=1) == 30.0
    assert p.cancel_refund(year=0, season_index=2) == 20.0
    assert p.cancel_refund(year=0, season_index=3) == 10.0
    assert p.cancel_refund(year=1, season_index=0) == 0.0  # exactly expired
    assert p.cancel_refund(year=2, season_index=0) == 0.0  # past expiry


def test_cancel_refund_zero_for_inactive_policy():
    p = _policy()
    p.active = False
    assert p.cancel_refund(year=0, season_index=1) == 0.0


def test_player_cancel_insurance_deactivates_policy_and_returns_refund():
    holder = Player(player_id=1, name="Farmer", roles=[ROLES["Farmer"]],
                    dollops=0.0, is_human=True)
    pol = _policy(premium=80.0, purchased_tick=0, expires_at_tick=4)
    holder.add_insurance_policy(pol)
    refund = holder.cancel_insurance_policy(pol.policy_id, year=0, season_index=1)
    assert refund == 60.0  # 3/4 of 80
    assert pol.active is False
    # Re-cancelling returns 0
    assert holder.cancel_insurance_policy(pol.policy_id, year=0, season_index=1) == 0.0


def test_player_cancel_unknown_policy_returns_zero():
    holder = Player(player_id=1, name="Farmer", roles=[ROLES["Farmer"]],
                    dollops=0.0, is_human=True)
    assert holder.cancel_insurance_policy(99, year=0, season_index=0) == 0.0


# ===========================================================================
# Insurance — action-level end-to-end
# ===========================================================================

def test_action_manage_insurance_cancels_policy_and_transfers_refund():
    banker = Player(player_id=0, name="Banker", roles=[ROLES["Banker"]],
                    dollops=100.0, is_human=True)
    holder = Player(player_id=1, name="Farmer", roles=[ROLES["Farmer"]],
                    dollops=50.0, is_human=True)
    pol = InsurancePolicy(
        policy_id=1, policy_type="life",
        holder_player_id=holder.player_id, banker_player_id=banker.player_id,
        premium_paid=40.0, purchased_tick=0, expires_at_tick=4,
    )
    holder.add_insurance_policy(pol)

    # quantities: [pick policy #1]; confirm: yes
    io = ScriptedIO(quantities=[1], confirms=[True])
    ledger = LoanLedger()
    tm = _turn_manager([banker, holder], ledger, io)
    result = TurnResult(player_id=holder.player_id, season=1, year=0)

    tm._action_manage_insurance(holder, result, year=0, season_index=1)

    # 3/4 of 40 = 30 Dp refund
    assert pol.active is False
    assert banker.dollops == 70.0  # paid out 30
    assert holder.dollops == 80.0  # received 30
    assert any("cancelled" in a for a in result.actions_taken)


def test_action_manage_insurance_returns_when_no_active_policies():
    holder = Player(player_id=1, name="Farmer", roles=[ROLES["Farmer"]],
                    dollops=50.0, is_human=True)
    io = ScriptedIO()
    ledger = LoanLedger()
    tm = _turn_manager([holder], ledger, io)
    result = TurnResult(player_id=holder.player_id, season=0, year=0)
    tm._action_manage_insurance(holder, result, year=0, season_index=0)
    assert result.actions_taken == []


def test_action_manage_insurance_cancel_aborts_on_confirm_no():
    banker = Player(player_id=0, name="Banker", roles=[ROLES["Banker"]],
                    dollops=100.0, is_human=True)
    holder = Player(player_id=1, name="Farmer", roles=[ROLES["Farmer"]],
                    dollops=50.0, is_human=True)
    pol = InsurancePolicy(
        policy_id=1, policy_type="life",
        holder_player_id=holder.player_id, banker_player_id=banker.player_id,
        premium_paid=40.0, purchased_tick=0, expires_at_tick=4,
    )
    holder.add_insurance_policy(pol)

    io = ScriptedIO(quantities=[1], confirms=[False])
    tm = _turn_manager([banker, holder], LoanLedger(), io)
    result = TurnResult(player_id=holder.player_id, season=1, year=0)

    tm._action_manage_insurance(holder, result, year=0, season_index=1)

    assert pol.active is True  # unchanged
    assert banker.dollops == 100.0
    assert holder.dollops == 50.0
    assert result.actions_taken == []
