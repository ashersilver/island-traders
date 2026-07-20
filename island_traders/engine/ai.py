from __future__ import annotations
from math import ceil
from collections.abc import Callable
from ..models.player import EQUIPMENT_RESOURCE_CAPITAL, Player
from ..models.market import Market
from ..models.resource import ResourceType, NON_TRADABLE_RESOURCES
from ..models.deal import DealProposal, DealStatus
from ..engine.events import EventResult
from ..engine.cycle import BusinessCycleSnapshot
from ..engine.production import ProductionEngine
from ..engine.trading import TradingEngine
from ..engine.revenue import revenue_opportunities
from ..engine.flu import vaccine_doses_needed
from ..models.insurance import InsurancePolicy
from ..models.training import (
    TrainingCapacityError,
    campus_has_technical_workshop,
    settling_seasons_on_return,
    training_duration,
)
from ..models.loan import LoanLedger, LoanStatus, banker_quote_rate, posted_funding_rates
from ..models.profession import Profession
from ..models.equity import UNISSUED_HOLDER, fair_value, share_price
from ..constants import (
    BASE_PRICES, MANUFACTURER_PRODUCT_LINES, PRODUCER_PRODUCTIVITY_MULTIPLIER,
    PRODUCTION_INPUTS,
    WORKPLACE_RISK, INSURANCE_BASE_PREMIUM, INSURANCE_DURATION_SEASONS,
    MBA_RESERVE_RATIO_BASE, MBA_RESERVE_RATIO_QUALIFIED,
    MBA_QUALIFIED_THRESHOLD, ACTUARIAL_EVALUATION_COST,
    STARTING_WORKERS_BY_PROFESSION, TRAINEE_FOOD_ACCOM_PER_SEASON,
    EQUIPMENT_AI_WARRANTY_MIN_COST,
    EQUIPMENT_REPAIR_SHIP_FREIGHT,
    EQUIPMENT_WARRANTY_ANNUAL_RATE,
    FLU_SEASON,
    MANUFACTURER_DURABLE_OUTPUTS,
    CE_ANNUAL_PER_MANAGER,
)
from ..constants_capacity import CAPITAL_CATALOGUE
from ..models.capacity import find_item, items_for_role

AI_TARGET_PRODUCTION_RUNS = 2
AI_OFFER_MARKUP = 1.0
AI_ARBITRAGE_MIN_MARGIN = 0.05
AI_MIN_LOAN_PRINCIPAL = 50.0
AI_DEBT_CEILING_MULTIPLIER = 2.0
AI_WORKING_CAPITAL_LOAN_FRACTION = 0.12
AI_DEBT_CEILING_WEALTH_FRACTION = 0.35
AI_MAX_WORKING_CAPITAL_LOAN = 250.0
AI_PERSONAL_CASH_RESERVE = 100.0
AI_EQUIPMENT_INPUT_RUNS = 5
AI_EQUIPMENT_INPUTS = {
    ResourceType.FARM_MACHINERY,
    ResourceType.MINING_EQUIPMENT,
    ResourceType.REAGENTS,
    ResourceType.MEDICAL_DEVICES,
    ResourceType.TRANSPORT_EQUIPMENT,
}
AI_LIST_ONLY_WITH_BID = {
    ResourceType.PATENTS,
    ResourceType.PASSENGER_SEATS,
}
AI_REPLACEMENT_TRAINING_ROLES = {"Farmer", "Miner", "Transporter", "Manufacturer"}
AI_TRAINING_CASH_RESERVE = 75.0
AI_INSURANCE_CASH_RESERVE = 125.0
AI_INSURANCE_MIN_INJURY_RATE = 0.02
AI_INSURANCE_MIN_FATALITY_RATE = 0.005
AI_VACCINE_CASH_RESERVE = 50.0
AI_HEALTH_QOL_COVERAGE_THRESHOLD = 0.5
AI_HEALTH_QOL_CASH_RESERVE = 50.0
AI_SPARES_TARGET_STOCK = 2


class AIStrategy:
    """
    Deterministic greedy rule-based bot for fast local play and simulations.

    This is intentionally a heuristic player, not an LLM-backed human-like
    player. Keep this path cheap, reproducible, and engine-local; see
    requirements/llm-player-adapter.md for the proposed LLM player adapter.

    Priority each turn:
    1. Review peer deals using observable market value.
    2. Buy or bid for missing production inputs.
    3. Produce if inputs are satisfied.
    4. Sell surplus production and opportunistically capture visible arbitrage.
    Training is handled by TurnManager via _ai_educator_respond / _auto_arrange_transport.
    """

    def __init__(self, target_production_runs: int = AI_TARGET_PRODUCTION_RUNS):
        self.target_production_runs = max(1, target_production_runs)

    def _mba_banker_count(self, banker: Player) -> int:
        return sum(
            1 for worker in banker.workforce.active_workers
            if worker.profession == Profession.BANKER.value
            and getattr(worker, "has_mba", False)
        )

    def _banker_reserve_ratio(self, banker: Player) -> float:
        if self._mba_banker_count(banker) >= MBA_QUALIFIED_THRESHOLD:
            return MBA_RESERVE_RATIO_QUALIFIED
        return MBA_RESERVE_RATIO_BASE

    def _banker_active_loan_cap(self, banker: Player) -> int:
        n_bankers = banker.workforce.count_profession(Profession.BANKER.value)
        return max(1, 2 * n_bankers)

    def _banker_active_loan_count(
        self, banker: Player, loan_ledger: LoanLedger
    ) -> int:
        return sum(
            1 for loan in loan_ledger.loans
            if loan.lender_id == banker.player_id
            and loan.status == LoanStatus.ACTIVE
        )

    def _one_season_input_cost(
        self,
        player: Player,
        market: Market,
        season_name: str,
        product_line: str | None = None,
    ) -> float:
        inputs = player.all_required_inputs(season_name, product_line)
        cost = sum(market.current_price(rtype) * qty for rtype, qty in inputs.items())
        return round(max(AI_MIN_LOAN_PRINCIPAL, cost), 1)

    def _capital_short_threshold(
        self,
        player: Player,
        market: Market,
        season_name: str,
        product_line: str | None = None,
    ) -> float:
        return self._one_season_input_cost(player, market, season_name, product_line)

    def _borrower_wealth(self, borrower: Player, market: Market) -> float:
        return max(
            borrower.dollops,
            borrower.total_wealth(market.current_prices(), capital_catalogue=CAPITAL_CATALOGUE),
        )

    def _borrower_debt_ceiling(
        self, borrower: Player, market: Market, loan_ledger: LoanLedger
    ) -> float:
        wealth = self._borrower_wealth(borrower, market)
        return max(
            AI_MIN_LOAN_PRINCIPAL,
            round(wealth * AI_DEBT_CEILING_WEALTH_FRACTION, 1),
        )

    def _ai_working_capital_principal(
        self,
        borrower: Player,
        market: Market,
        loan_ledger: LoanLedger,
        season_name: str,
        product_line: str | None = None,
    ) -> float:
        wealth = self._borrower_wealth(borrower, market)
        target_line = max(
            self._capital_short_threshold(borrower, market, season_name, product_line),
            min(AI_MAX_WORKING_CAPITAL_LOAN, wealth * AI_WORKING_CAPITAL_LOAN_FRACTION),
        )
        debt = loan_ledger.outstanding_debt(borrower.player_id)
        capacity = self._borrower_debt_ceiling(borrower, market, loan_ledger) - debt
        principal = min(target_line, capacity)
        if principal < AI_MIN_LOAN_PRINCIPAL:
            return 0.0
        return round(principal, 1)

    def _find_ai_banker(
        self,
        players: list[Player],
        exclude_player_id: int | None = None,
    ) -> Player | None:
        for candidate in players:
            if candidate.is_human or candidate.player_id == exclude_player_id:
                continue
            if any(role.name == "Banker" for role in candidate.roles):
                return candidate
        return None

    def _candidate_bankers(
        self,
        players: list[Player],
        exclude_player_id: int | None = None,
    ) -> list[Player]:
        return [
            candidate for candidate in players
            if candidate.player_id != exclude_player_id
            and any(role.name == "Banker" for role in candidate.roles)
        ]

    def _ai_issue_loan(
        self,
        banker: Player,
        borrower: Player,
        principal: float,
        loan_ledger: LoanLedger,
        year: int,
        season_index: int,
        cycle: BusinessCycleSnapshot | None = None,
    ) -> str | None:
        if borrower.is_human or banker.player_id == borrower.player_id:
            return None
        if principal <= 0:
            return None
        active = self._banker_active_loan_count(banker, loan_ledger)
        cap = self._banker_active_loan_cap(banker)
        if active >= cap:
            return (
                f"[AI] {banker.name} declined new loan: active-loan cap "
                f"reached ({active}/{cap})"
            )
        term_years = 1
        funding_rate = posted_funding_rates(year, season_index, cycle=cycle)[term_years]
        rate = banker_quote_rate(
            borrower, loan_ledger, principal, term_years, year, season_index,
            cycle=cycle,
        )
        reserve_ratio = self._banker_reserve_ratio(banker)
        own_share = round(reserve_ratio * principal, 2)
        if banker.dollops < own_share:
            return None
        external_share = max(0.0, round(principal - own_share, 2))

        loan = loan_ledger.create_loan(
            borrower_id=borrower.player_id,
            lender_id=banker.player_id,
            principal=principal,
            interest_rate=rate,
            issued_year=year,
            issued_season=season_index,
            term_years=term_years,
            own_committed=own_share,
            external_funded=external_share,
            posted_at_issue=funding_rate,
            reserve_ratio_at_issue=reserve_ratio,
        )
        if external_share > 0:
            loan_ledger.create_loan(
                borrower_id=banker.player_id,
                lender_id=-1,
                principal=external_share,
                interest_rate=funding_rate,
                issued_year=year,
                issued_season=season_index,
                term_years=term_years,
            )
            banker.receive_dollops(external_share)
        banker.dollops -= principal
        borrower.receive_dollops(principal)
        return (
            f"[AI] {banker.name} issued Loan #{loan.loan_id} to {borrower.name} "
            f"for {principal:.1f} Dp at {rate*100:.1f}%"
        )

    def _ai_offer_loans(
        self,
        banker: Player,
        other_players: list[Player],
        market: Market,
        loan_ledger: LoanLedger | None,
        season_name: str,
        year: int,
        season_index: int,
        cycle: BusinessCycleSnapshot | None = None,
    ) -> list[str]:
        if loan_ledger is None:
            return []
        actions: list[str] = []
        for borrower in other_players:
            if borrower.player_id == banker.player_id or borrower.is_human:
                continue
            if any(
                loan.borrower_id == borrower.player_id
                for loan in loan_ledger.active_loans_for(borrower.player_id)
            ):
                continue
            debt_ceiling = self._borrower_debt_ceiling(borrower, market, loan_ledger)
            if loan_ledger.outstanding_debt(borrower.player_id) >= debt_ceiling:
                continue
            principal = self._ai_working_capital_principal(
                borrower, market, loan_ledger, season_name
            )
            if principal <= 0:
                continue
            action = self._ai_issue_loan(
                banker, borrower, principal, loan_ledger, year, season_index,
                cycle=cycle,
            )
            if action:
                actions.append(action)
        return actions

    def _ai_take_loan_if_short(
        self,
        player: Player,
        market: Market,
        other_players: list[Player],
        loan_ledger: LoanLedger | None,
        season_name: str,
        year: int,
        season_index: int,
        product_line: str | None = None,
        cycle: BusinessCycleSnapshot | None = None,
    ) -> list[str]:
        if any(role.name == "Banker" for role in player.roles):
            return []
        threshold = self._capital_short_threshold(
            player, market, season_name, product_line
        )
        if player.dollops >= threshold:
            return []
        if loan_ledger is not None and not any(
            loan.borrower_id == player.player_id
            for loan in loan_ledger.active_loans_for(player.player_id)
        ):
            debt_capacity = (
                self._borrower_debt_ceiling(player, market, loan_ledger)
                - loan_ledger.outstanding_debt(player.player_id)
            )
            needed = max(AI_MIN_LOAN_PRINCIPAL, threshold - player.dollops)
            principal = round(min(needed, debt_capacity), 1)
            if principal >= AI_MIN_LOAN_PRINCIPAL:
                for banker in self._candidate_bankers(
                    other_players, exclude_player_id=player.player_id
                ):
                    action = self._ai_issue_loan(
                        banker, player, principal, loan_ledger, year, season_index,
                        cycle=cycle,
                    )
                    if action:
                        return [action]

        action = self._ai_recapitalize_if_short(player, market, threshold)
        return [action] if action else []

    def _ai_recapitalize_if_short(
        self,
        player: Player,
        market: Market,
        threshold: float,
    ) -> str | None:
        if player.cap_table is None or player.dollops >= threshold:
            return None
        owner = getattr(player, "owner", None)
        owner_cash = (
            float(getattr(owner, "personal_cash", 0.0))
            if owner is not None else player.personal_cash
        )
        available_cash = owner_cash - AI_PERSONAL_CASH_RESERVE
        if available_cash <= 0:
            return None
        unissued = player.cap_table.unissued()
        if unissued <= 0:
            return None
        price = share_price(
            fair_value(
                player.total_wealth(
                    market.current_prices(),
                    capital_catalogue=CAPITAL_CATALOGUE,
                ),
                player.wealth_history,
            )
        )
        needed_cash = threshold - player.dollops
        needed_shares = max(1, ceil(needed_cash / price))
        affordable_shares = int(available_cash // price)
        shares = min(unissued, needed_shares, affordable_shares)
        if shares <= 0:
            return None
        cost = round(shares * price, 1)
        if owner is not None:
            owner.personal_cash = round(owner.personal_cash - cost, 1)
        else:
            player.personal_cash = round(player.personal_cash - cost, 1)
        player.dollops = round(player.dollops + cost, 1)
        owner_key = str(getattr(owner, "owner_id", player.player_id))
        player.cap_table.transfer(UNISSUED_HOLDER, owner_key, shares)
        if owner is not None:
            island_key = str(player.player_id)
            owner.holdings[island_key] = owner.holdings.get(island_key, 0) + shares
        else:
            player.holdings[owner_key] = player.holdings.get(owner_key, 0) + shares
        return (
            f"[AI] {player.name} recapitalized with {shares} unissued share(s) "
            f"for {cost:.1f} Dp"
        )

    def _ai_rollover_due_loans(
        self,
        player: Player,
        loan_ledger: LoanLedger | None,
        year: int,
        season_index: int,
        cycle: BusinessCycleSnapshot | None = None,
    ) -> list[str]:
        if loan_ledger is None:
            return []
        actions: list[str] = []
        for loan in loan_ledger.active_loans_for(player.player_id):
            if loan.borrower_id != player.player_id or loan.lender_id < 0:
                continue
            seasons_to_maturity = (
                (loan.maturity_year - year) * 4
                + (loan.maturity_season - season_index)
            )
            if seasons_to_maturity > 1 or player.dollops >= loan.repayment_amount:
                continue
            new_rate = banker_quote_rate(
                player, loan_ledger, loan.repayment_amount, 1, year, season_index,
                cycle=cycle,
            )
            try:
                new_loan = loan_ledger.rollover_loan(
                    loan.loan_id, new_rate, 1, year, season_index
                )
            except ValueError:
                continue
            actions.append(
                f"[AI] {player.name} rolled over Loan #{loan.loan_id} "
                f"into Loan #{new_loan.loan_id}"
            )
            break
        return actions

    def _ai_invest_unclaimed_catalogue_item(
        self,
        player: Player,
        year: int,
        season_index: int,
        other_players: list[Player] | None = None,
    ) -> list[str]:
        seen: set[str] = set()
        unclaimed = []
        for role in player.roles:
            for item in items_for_role(CAPITAL_CATALOGUE, role.name):
                if item.item_id in seen:
                    continue
                seen.add(item.item_id)
                if player.capital_inventory.get(item.item_id, 0) <= 0:
                    unclaimed.append(item)
        if not unclaimed:
            return []
        item = min(unclaimed, key=lambda catalogue_item: catalogue_item.cost)
        premium = (
            round(item.cost * EQUIPMENT_WARRANTY_ANNUAL_RATE, 2)
            if item.cost >= EQUIPMENT_AI_WARRANTY_MIN_COST else 0.0
        )
        if player.dollops <= (item.cost + premium) * 2:
            return []
        player.dollops -= item.cost
        current_tick = year * 4 + season_index
        player.add_capital(item.item_id, 1, acquired_tick=current_tick)
        warranty_note = ""
        if premium > 0:
            player.add_capital_warranty(item.item_id, 1)
            manufacturer = next(
                (
                    candidate for candidate in (other_players or [])
                    if candidate.player_id != player.player_id
                    and any(r.name == "Manufacturer" for r in candidate.roles)
                ),
                None,
            )
            if manufacturer is not None and player.dollops >= premium:
                player.spend_dollops(premium)
                manufacturer.receive_dollops(premium)
                warranty_note = f" + {premium:.0f} Dp warranty"
        return [
            f"[AI] {player.name} invested {item.cost:.0f} Dp in {item.name}"
            f"{warranty_note}"
        ]

    def _ai_offer_insurance(
        self,
        banker: Player,
        other_players: list[Player],
        season_name: str,
        year: int,
        season_index: int,
    ) -> list[str]:
        """Banker AI proactively sells base-premium policies to uninsured AI players."""
        actions: list[str] = []
        if banker.workforce.count_profession(Profession.ACTUARY.value) <= 0:
            return actions
        purchased_tick = year * 4 + season_index
        expires_at = purchased_tick + INSURANCE_DURATION_SEASONS
        for target in other_players:
            if target.player_id == banker.player_id or target.is_human:
                continue
            if not self._needs_ai_workplace_insurance(target):
                continue
            for role in target.roles:
                risk = WORKPLACE_RISK.get(role.name, {})
                if not self._risk_is_insurable_for_ai(risk):
                    continue
                for policy_type in ("life", "medical"):
                    if target.has_active_insurance(policy_type, year, season_index):
                        continue
                    premium = INSURANCE_BASE_PREMIUM[policy_type]
                    if target.dollops < premium or banker.dollops < ACTUARIAL_EVALUATION_COST:
                        continue
                    target.spend_dollops(premium)
                    banker.receive_dollops(premium)
                    banker.spend_dollops(ACTUARIAL_EVALUATION_COST)
                    policy = InsurancePolicy(
                        policy_id=len(target.insurance_policies) + 1,
                        policy_type=policy_type,
                        holder_player_id=target.player_id,
                        banker_player_id=banker.player_id,
                        premium_paid=premium,
                        purchased_tick=purchased_tick,
                        expires_at_tick=expires_at,
                    )
                    target.add_insurance_policy(policy)
                    actions.append(
                        f"[AI] {banker.name} issued {policy_type} insurance to "
                        f"{target.name} for {premium:.0f} Dp"
                    )
        return actions

    def _risk_is_insurable_for_ai(self, risk: dict[str, float]) -> bool:
        return (
            risk.get("injury_rate", 0.0) >= AI_INSURANCE_MIN_INJURY_RATE
            or risk.get("fatality_rate", 0.0) >= AI_INSURANCE_MIN_FATALITY_RATE
        )

    def _needs_ai_workplace_insurance(self, player: Player) -> bool:
        return any(
            self._risk_is_insurable_for_ai(WORKPLACE_RISK.get(role.name, {}))
            for role in player.roles
        )

    def _ai_buy_workplace_insurance(
        self,
        player: Player,
        other_players: list[Player],
        year: int,
        season_index: int,
    ) -> list[str]:
        if player.is_human or any(role.name == "Banker" for role in player.roles):
            return []
        if not self._needs_ai_workplace_insurance(player):
            return []
        banker = next(
            (
                candidate for candidate in self._candidate_bankers(
                    other_players, exclude_player_id=player.player_id
                )
                if not candidate.is_human
                and candidate.workforce.count_profession(Profession.ACTUARY.value) > 0
            ),
            None,
        )
        if banker is None:
            return []

        actions: list[str] = []
        purchased_tick = year * 4 + season_index
        expires_at = purchased_tick + INSURANCE_DURATION_SEASONS
        for policy_type in ("life", "medical"):
            if player.has_active_insurance(policy_type, year, season_index):
                continue
            premium = INSURANCE_BASE_PREMIUM[policy_type]
            if player.dollops < premium + AI_INSURANCE_CASH_RESERVE:
                continue
            if banker.dollops < ACTUARIAL_EVALUATION_COST:
                continue
            player.spend_dollops(premium)
            banker.receive_dollops(premium)
            banker.spend_dollops(ACTUARIAL_EVALUATION_COST)
            policy = InsurancePolicy(
                policy_id=len(player.insurance_policies) + 1,
                policy_type=policy_type,
                holder_player_id=player.player_id,
                banker_player_id=banker.player_id,
                premium_paid=premium,
                purchased_tick=purchased_tick,
                expires_at_tick=expires_at,
            )
            player.add_insurance_policy(policy)
            actions.append(
                f"[AI] {player.name} bought {policy_type} insurance from "
                f"{banker.name} for {premium:.0f} Dp"
            )
        return actions

    def _ai_training_skill_deficits(self, player: Player, training_registry) -> dict[str, int]:
        required: dict[str, int] = {}
        for role in player.roles:
            if role.name not in AI_REPLACEMENT_TRAINING_ROLES:
                continue
            for profession, count in STARTING_WORKERS_BY_PROFESSION.get(role.name, []):
                required[profession] = required.get(profession, 0) + count
        if not required:
            return {}

        current: dict[str, int] = {}
        for worker in player.workforce.workers:
            current[worker.profession] = current.get(worker.profession, 0) + 1
        if training_registry is not None:
            workers_by_id = {worker.worker_id: worker for worker in player.workforce.workers}
            for req in training_registry.active_for_player(player.player_id):
                incoming = sum(
                    1
                    for worker_id in req.worker_ids
                    if workers_by_id.get(worker_id)
                    and workers_by_id[worker_id].profession == Profession.UNSKILLED.value
                )
                current[req.target_profession] = current.get(req.target_profession, 0) + incoming

        return {
            profession: needed - current.get(profession, 0)
            for profession, needed in required.items()
            if needed > current.get(profession, 0)
        }

    def _ai_request_replacement_training(
        self,
        player: Player,
        other_players: list[Player],
        market: Market,
        training_registry,
        year: int,
        season_index: int,
    ) -> list[str]:
        if player.is_human or training_registry is None:
            return []
        deficits = self._ai_training_skill_deficits(player, training_registry)
        if not deficits:
            return []

        educators = [
            candidate for candidate in other_players
            if candidate.player_id != player.player_id
            and any(role.name == "Educator" for role in candidate.roles)
        ]
        if not educators:
            return []
        educator = educators[0]

        needed_workers = sum(deficits.values())
        unskilled_ids = [
            worker_id for worker_id in player.workforce.get_unskilled_ids(needed_workers)
            if worker_id not in training_registry.reserved_worker_ids(player.player_id)
        ]
        shortage = max(0, needed_workers - len(unskilled_ids))
        if shortage > 0 and player.available_unskilled > 0:
            recruited = player.recruit_workers(min(shortage, player.available_unskilled))
            if recruited:
                unskilled_ids = [
                    worker_id for worker_id in player.workforce.get_unskilled_ids(needed_workers)
                    if worker_id not in training_registry.reserved_worker_ids(player.player_id)
                ]
        if not unskilled_ids:
            return []

        actions: list[str] = []
        worker_offset = 0
        ticket_price = market.current_price(ResourceType.PASSENGER_SEATS)
        capacity = training_registry.capacity_summary(year, season_index)
        for profession, deficit in deficits.items():
            remaining_capacity = capacity.get(profession, {}).get("remaining", 0)
            count = min(deficit, remaining_capacity, len(unskilled_ids) - worker_offset)
            if count <= 0:
                continue
            worker_ids = unskilled_ids[worker_offset:worker_offset + count]
            has_workshop = campus_has_technical_workshop(educator)
            duration = training_duration(
                profession,
                has_technical_workshop=has_workshop,
            )
            courses = max(1, ceil(count / 12))
            fee = round(
                20.0 * count
                + TRAINEE_FOOD_ACCOM_PER_SEASON * count * duration
                + ticket_price * count
                + market.current_price(ResourceType.EXPERTISE) * courses * duration,
                1,
            )
            settling = settling_seasons_on_return(
                profession,
                has_technical_workshop=has_workshop,
            )
            if player.dollops < fee + AI_TRAINING_CASH_RESERVE:
                break
            try:
                req = training_registry.propose(
                    requester_id=player.player_id,
                    worker_ids=worker_ids,
                    educator_id=educator.player_id,
                    dollops_to_educator=fee,
                    target_profession=profession,
                    year=year,
                    season=season_index,
                    transport_mode="air_ticket",
                    duration_seasons=duration,
                    settling_seasons_on_return=settling,
                )
            except TrainingCapacityError:
                continue
            worker_offset += count
            actions.append(
                f"[AI] {player.name} requested replacement training "
                f"batch #{req.batch_id}: {count}x {profession}"
            )
            if worker_offset >= len(unskilled_ids):
                break
        return actions

    def _choose_product_line(
        self,
        player: Player,
        market: Market,
        demand_players: list[Player] | None = None,
        training_registry=None,
        season_name: str = "Spring",
    ) -> str:
        """Pick the Manufacturer product line with the strongest unmet demand."""
        has_human_demand = False
        if demand_players is not None:
            has_human_demand = self._has_human_equipment_demand(
                demand_players, training_registry=training_registry
            )
        # Spares bids are excluded from the routing gate: every capital-owning
        # AI now posts a small standing Spares bid (2 kits), so counting them
        # made has_visible_bid ~always true and re-routed every sim game into
        # the profit chooser. Spares still competes on score inside whichever
        # path runs — it just doesn't get to steer the routing.
        has_visible_bid = any(
            market.best_bid(ResourceType(line["output"])) is not None
            for line_key, line in MANUFACTURER_PRODUCT_LINES.items()
            if line_key != "Spares"
        )

        current_line = getattr(
            player, "ai_product_line", next(iter(MANUFACTURER_PRODUCT_LINES))
        )
        if demand_players is not None and not has_human_demand and has_visible_bid:
            return self._choose_product_line_profit(player, market)
        structural_opportunity_scores = False
        if demand_players is not None:
            opportunities = revenue_opportunities(
                player, market, demand_players, season_name
            )
            scores = {
                opp["product_line"]: opp["score"]
                for opp in opportunities
                if opp.get("product_line") in MANUFACTURER_PRODUCT_LINES
            }
            if not has_visible_bid and not has_human_demand:
                for line_key, line in MANUFACTURER_PRODUCT_LINES.items():
                    if ResourceType(line["output"]) in EQUIPMENT_RESOURCE_CAPITAL:
                        scores[line_key] = 0.0
            structural_opportunity_scores = bool(scores)
        else:
            scores = {}
        if not scores:
            scores = {
                line_key: self._manufacturer_demand_score(player, market, line_key)
                for line_key in MANUFACTURER_PRODUCT_LINES
            }
        else:
            # The structural revenue_opportunities model doesn't cover every
            # line (Spares in particular) — backfill missing lines with the
            # demand score so max()/comparisons below never KeyError and a
            # bid-pulled line can still win on merit.
            for line_key in MANUFACTURER_PRODUCT_LINES:
                scores.setdefault(
                    line_key,
                    self._manufacturer_demand_score(player, market, line_key),
                )
        feasible = [
            line_key for line_key in MANUFACTURER_PRODUCT_LINES
            if self._manufacturer_line_feasible(player, line_key)
        ]
        # Spares competes in the normal scoring like any other line (repair
        # bids from other islands pull its score up via bid_pull). The ONLY
        # hard override is a genuine emergency: own capital sits failed with
        # no kit on hand, so a repair is blocked/premium-priced right now.
        # The first cut of this override fired on ANY standing bid or
        # whenever stock dipped below 4 (== the starting seed), chronically
        # diverting the Manufacturer from lines worth several times more —
        # 1000-game sim: 10.4% -> 3.3% win rate. Score-competition + narrow
        # emergency restores the opportunity-cost tradeoff.
        if "Spares" in feasible and self._spares_emergency(player):
            player.ai_product_line = "Spares"
            player.ai_product_line_human_demand = has_human_demand
            return "Spares"
        if not feasible:
            chosen = max(scores, key=lambda line_key: scores[line_key])
            player.ai_product_line = chosen
            player.ai_product_line_human_demand = has_human_demand
            return chosen
        top_line = max(feasible, key=lambda line_key: scores[line_key])
        sticky_margin = 1.15 if structural_opportunity_scores else 1.10
        if (
            current_line in feasible
            and scores[top_line] <= scores[current_line] * sticky_margin
        ):
            chosen = current_line
        else:
            chosen = top_line
        player.ai_product_line = chosen
        player.ai_product_line_human_demand = has_human_demand
        return chosen

    def _choose_product_line_profit(self, player: Player, market: Market) -> str:
        """Legacy profit/bid chooser used when there is no human demand signal."""
        best_line = next(iter(MANUFACTURER_PRODUCT_LINES))
        best_score = float("-inf")
        # A standing bid narrows the candidate set (real demand signal) —
        # except Spares: the ubiquitous 2-kit buffer bids from other AIs
        # would otherwise make Spares the ONLY candidate whenever equipment
        # bids are absent, crowding out lines worth 4-5x more (this tanked
        # the Manufacturer's sim win rate 10.4% -> 3.3%). Spares still
        # competes on score whenever the candidate set includes it.
        bid_lines = [
            line_key for line_key, line in MANUFACTURER_PRODUCT_LINES.items()
            if line_key != "Spares"
            and market.best_bid(ResourceType(line["output"])) is not None
        ]
        candidates = bid_lines or list(MANUFACTURER_PRODUCT_LINES)
        for line_key, line in MANUFACTURER_PRODUCT_LINES.items():
            if line_key not in candidates:
                continue
            output_rt = ResourceType(line["output"])
            bid = market.best_bid(output_rt)
            unit_price = bid.price_per_unit if bid is not None else market.current_price(output_rt)
            bid_pull = min(bid.remaining, line["qty"]) if bid is not None else 0
            revenue = unit_price * line["qty"]
            input_cost = sum(
                market.current_price(ResourceType(r)) * qty
                for r, qty in line["inputs"].items()
            )
            freight = self._manufacturer_freight_surcharge(line_key, line["qty"])
            input_cost += market.current_price(ResourceType.FREIGHT) * freight
            already_have = sum(
                min(player.inventory.get(ResourceType(r)), qty)
                for r, qty in line["inputs"].items()
            )
            score = revenue - input_cost + already_have * 2 + bid_pull * unit_price
            if score > best_score:
                best_score = score
                best_line = line_key
        player.ai_product_line = best_line
        player.ai_product_line_human_demand = False
        return best_line

    def _has_human_equipment_demand(
        self,
        players: list[Player],
        training_registry=None,
    ) -> bool:
        """Does at least one human player demand Manufacturer-produced equipment?

        Two paths trigger demand:

        - **Direct**: the human's role consumes a Manufacturer output
          (e.g. Miner needs MiningEquipment, Doctor needs MedicalDevices).
          PR #46's original behaviour.

        - **Indirect** (2026-05-27 training-expertise-deadlock brief): the
          human has pending training requests or workers already in
          training.  Both signal that the Educator must produce Expertise
          to fulfil them, which in turn requires Reagents from
          the Manufacturer.  Without this, a game with one human Miner
          (Mining is direct-demand for MiningEquipment, but NOT for
          LabEquipment) leaves the Educator's Expertise pipeline
          unblocked → AyaySir-style 9-season deadlock.
        """
        equipment_outputs = {
            ResourceType(line["output"]).value
            for line in MANUFACTURER_PRODUCT_LINES.values()
        }
        for candidate in players:
            if not candidate.is_human:
                continue
            for resource, (role_name, item_id) in EQUIPMENT_RESOURCE_CAPITAL.items():
                if resource.value not in equipment_outputs:
                    continue
                if any(role.name == role_name for role in candidate.roles):
                    if candidate.capital_count(item_id) <= 0:
                        return True
            # Direct path.
            for role in candidate.roles:
                if any(
                    resource in equipment_outputs
                    for resource in PRODUCTION_INPUTS.get(role.name, {})
                ):
                    return True
            # Indirect path — workers already dispatched/in-training.
            # No registry lookup needed; the workforce roster knows.
            if candidate.workforce.training_count > 0:
                return True
            # Indirect path — pending training requests this human filed
            # but the Educator hasn't approved yet (the deadlock case).
            if training_registry is not None:
                try:
                    pending = training_registry.pending_for_requester(
                        candidate.player_id
                    )
                except AttributeError:
                    pending = None
                if pending:
                    return True
        return False

    def _spares_emergency(self, player: Player) -> bool:
        """Own capital failed with zero kits on hand — repair is blocked or
        premium-priced until a Spares run happens. This is the only condition
        that overrides normal product-line scoring."""
        if player.spares_capacity() <= 0:
            return False
        needed = self._max_failed_repair_spares_required(player)
        return needed > 0 and player.inventory.get(ResourceType.SPARES) < needed

    def _manufacturer_demand_score(
        self, player: Player, market: Market, line_key: str
    ) -> float:
        line = MANUFACTURER_PRODUCT_LINES[line_key]
        output = ResourceType(line["output"])
        current_price = market.current_price(output)
        base_price = BASE_PRICES.get(output.value, current_price)
        demand_units = self._manufacturer_demand_units(output)
        visible_supply = sum(offer.remaining for offer in market.available_offers(output))
        supply_memory = getattr(player, "ai_equipment_supply_memory", {})
        remembered_supply = supply_memory.get(output.value, 0)
        supply_units = (
            player.inventory.get(output)
            + visible_supply
            + remembered_supply
            + line["qty"]
        )
        unmet = max(0, demand_units - supply_units)
        bid = market.best_bid(output)
        bid_pull = bid.remaining if bid is not None else 0
        visible_bid_pull = bid_pull * PRODUCER_PRODUCTIVITY_MULTIPLIER
        return (current_price / base_price) * (unmet + visible_bid_pull)

    def _manufacturer_demand_units(self, output: ResourceType) -> int:
        per_season = self._manufacturer_per_season_demand_units(output)
        return per_season * PRODUCER_PRODUCTIVITY_MULTIPLIER * AI_EQUIPMENT_INPUT_RUNS

    def _manufacturer_per_season_demand_units(self, output: ResourceType) -> int:
        per_season = 0
        equipment_mapping = EQUIPMENT_RESOURCE_CAPITAL.get(output)
        if equipment_mapping is not None:
            per_season += 1
        for role_inputs in PRODUCTION_INPUTS.values():
            per_season += role_inputs.get(output.value, 0)
        for line in MANUFACTURER_PRODUCT_LINES.values():
            per_season += line["inputs"].get(output.value, 0)
        return per_season

    def _manufacturer_line_feasible(self, player: Player, line_key: str) -> bool:
        line = MANUFACTURER_PRODUCT_LINES[line_key]
        if not all(
            player.inventory.get(ResourceType(resource)) >= qty
            for resource, qty in line["inputs"].items()
        ):
            return False
        build_cost = float(line.get("build_cost_dollops", 0.0)) * int(line.get("qty", 0))
        if build_cost > player.dollops:
            return False
        if line.get("output") in MANUFACTURER_DURABLE_OUTPUTS:
            return ProductionEngine().manufacturer_durable_allowance_remaining(player) > 0
        return True

    def _manufacturer_freight_surcharge(self, product_line: str | None, qty: int) -> int:
        if not product_line or product_line not in MANUFACTURER_PRODUCT_LINES:
            return 0
        freight_per_unit = MANUFACTURER_PRODUCT_LINES[product_line]["freight_per_unit"]
        if freight_per_unit <= 0 or qty <= 0:
            return 0
        board_scale_qty = max(1, round(qty / PRODUCER_PRODUCTIVITY_MULTIPLIER))
        return freight_per_unit * board_scale_qty

    def _inputs_for_ai_purchase(
        self,
        player: Player,
        season_name: str,
        product_line: str | None,
        banker_office_goods: bool = False,
    ) -> dict[ResourceType, int]:
        inputs = dict(player.all_required_inputs(season_name, product_line))
        if any(role.name == "Manufacturer" for role in player.roles):
            line = MANUFACTURER_PRODUCT_LINES.get(
                product_line or next(iter(MANUFACTURER_PRODUCT_LINES))
            )
            if line:
                freight = self._manufacturer_freight_surcharge(product_line, line["qty"])
                if freight:
                    inputs[ResourceType.FREIGHT] = inputs.get(ResourceType.FREIGHT, 0) + freight
        for resource, (role_name, item_id) in EQUIPMENT_RESOURCE_CAPITAL.items():
            if (
                any(role.name == role_name for role in player.roles)
                and player.capital_count(item_id) <= 0
            ):
                inputs[resource] = max(inputs.get(resource, 0), 1)
        unresolved_repairs = sum(
            max(0, count - self._repair_in_progress_count(player, item_id))
            for item_id, count in player.failed_capital.items()
        )
        if unresolved_repairs > 0:
            inputs[ResourceType.FREIGHT] = max(
                inputs.get(ResourceType.FREIGHT, 0),
                unresolved_repairs * EQUIPMENT_REPAIR_SHIP_FREIGHT,
            )
        inputs.setdefault(ResourceType.OIL, 0)
        if (
            not any(role.name == "Manufacturer" for role in player.roles)
            and any(count > 0 for count in player.capital_inventory.values())
        ):
            target = self._spares_target_stock(player)
            missing_spares = max(0, target - player.inventory.get(ResourceType.SPARES))
            if missing_spares > 0:
                inputs[ResourceType.SPARES] = max(
                    inputs.get(ResourceType.SPARES, 0), missing_spares
                )
        if banker_office_goods:
            inputs[ResourceType.GOODS] = max(inputs.get(ResourceType.GOODS, 0), 1)
        ce_shortfall = self._ce_expertise_shortfall(player)
        if ce_shortfall > 0:
            inputs[ResourceType.EXPERTISE] = max(
                inputs.get(ResourceType.EXPERTISE, 0), ce_shortfall
            )
        return inputs

    def _ce_expertise_shortfall(self, player: Player) -> int:
        managers = player.ce_manager_count()
        if managers <= 0:
            return 0
        annual_need = managers * CE_ANNUAL_PER_MANAGER
        covered = player.ce_ytd() + player.inventory.get(ResourceType.EXPERTISE)
        return max(0, int(ceil(annual_need - covered)))

    def _banker_has_active_book(
        self,
        player: Player,
        other_players: list[Player],
        loan_ledger: LoanLedger | None,
        year: int,
        season_index: int,
    ) -> bool:
        if not any(role.name == "Banker" for role in player.roles):
            return False
        if loan_ledger is not None and any(
            loan.status == LoanStatus.ACTIVE
            and loan.lender_id == player.player_id
            and loan.borrower_id != player.player_id
            for loan in loan_ledger.all_loans()
        ):
            return True
        return any(
            policy.banker_player_id == player.player_id
            and policy.is_valid(year, season_index)
            for insured in [player] + other_players
            for policy in insured.insurance_policies
        )

    def _capacity_units_for_item(self, item_id: str) -> int:
        item = find_item(CAPITAL_CATALOGUE, item_id)
        return max(1, int(getattr(item, "capacity_units", 1))) if item else 1

    def _spares_target_stock(self, player: Player) -> int:
        max_units = max(
            (self._capacity_units_for_item(item_id)
             for item_id in player.capital_inventory),
            default=AI_SPARES_TARGET_STOCK,
        )
        return max(AI_SPARES_TARGET_STOCK, 2 * max_units)

    def _max_failed_repair_spares_required(self, player: Player) -> int:
        failed_item_ids = {
            item_id
            for item_id, units in player.capital_units.items()
            if any(unit.status == "failed" for unit in units)
        }
        return max(
            (self._capacity_units_for_item(item_id) for item_id in failed_item_ids),
            default=0,
        )

    def _repair_in_progress_count(self, player: Player, item_id: str) -> int:
        return sum(
            int(entry.get("count", 1))
            for entry in player.capital_repair_in_progress
            if entry.get("item_id") == item_id
        )

    def _farmer_visible_human_demand_output(
        self,
        player: Player,
        market: Market,
        other_players: list[Player],
        production_engine: ProductionEngine,
        event_result: EventResult,
        season_name: str,
    ) -> tuple[ResourceType, int] | None:
        if not any(role.name == "Farmer" for role in player.roles):
            return None
        humans = {candidate.player_id for candidate in other_players if candidate.is_human}
        options = {
            option["output"]: option
            for option in production_engine.production_options(player, event_result, season_name)
            if option["role"] == "Farmer"
        }
        for output in (ResourceType.FOOD, ResourceType.MEAT):
            bid = market.best_bid(output)
            option = options.get(output)
            if bid is None or option is None or bid.buyer_id not in humans:
                continue
            qty = min(option["max_qty"], bid.remaining)
            if qty > 0:
                return output, qty
        return None

    def _last_deal_price(self, trading_engine: TradingEngine, rtype: ResourceType) -> float | None:
        """Infer the latest cash/unit price from accepted one-resource deals."""
        for deal in reversed(trading_engine.ledger.deals):
            if deal.status != DealStatus.ACCEPTED:
                continue
            if deal.offer_resource == rtype and deal.offer_qty > 0 and deal.gold_sweetener < 0:
                return round(abs(deal.gold_sweetener) / deal.offer_qty, 2)
            if deal.request_resource == rtype and deal.request_qty > 0 and deal.gold_sweetener > 0:
                return round(deal.gold_sweetener / deal.request_qty, 2)
        return None

    def _valuation_price(
        self, market: Market, trading_engine: TradingEngine, rtype: ResourceType
    ) -> float:
        """Value goods from recent deals, then live asks, then formula price."""
        last_deal = self._last_deal_price(trading_engine, rtype)
        if last_deal is not None:
            return last_deal
        best_offer = market.best_offer(rtype)
        if best_offer is not None:
            return best_offer.price_per_unit
        return market.current_price(rtype)

    def _deal_value_for_player(
        self, deal: DealProposal, player_id: int, market: Market, trading_engine: TradingEngine
    ) -> tuple[float, float]:
        if player_id == deal.target_id:
            received = max(deal.gold_sweetener, 0)
            given = max(-deal.gold_sweetener, 0)
            if deal.offer_resource and deal.offer_qty > 0:
                received += deal.offer_qty * self._valuation_price(
                    market, trading_engine, deal.offer_resource
                )
            if deal.request_resource and deal.request_qty > 0:
                given += deal.request_qty * self._valuation_price(
                    market, trading_engine, deal.request_resource
                )
            return received, given

        received = max(-deal.gold_sweetener, 0)
        given = max(deal.gold_sweetener, 0)
        if deal.request_resource and deal.request_qty > 0:
            received += deal.request_qty * self._valuation_price(
                market, trading_engine, deal.request_resource
            )
        if deal.offer_resource and deal.offer_qty > 0:
            given += deal.offer_qty * self._valuation_price(
                market, trading_engine, deal.offer_resource
            )
        return received, given

    def _review_pending_deals(
        self,
        player: Player,
        market: Market,
        other_players: list[Player],
        trading_engine: TradingEngine,
        current_tick: int = 0,
    ) -> list[str]:
        """Accept profitable AI-targeted deals; reject deals that destroy value."""
        actions: list[str] = []
        players = {p.player_id: p for p in other_players}
        for deal in trading_engine.ledger.pending_for_player(player.player_id):
            proposer = players.get(deal.proposer_id)
            target = players.get(deal.target_id)
            if proposer is None or target is None:
                trading_engine.ledger.expire(deal.deal_id)
                actions.append(f"[AI] {player.name} let stale deal #{deal.deal_id} expire")
                continue
            received, given = self._deal_value_for_player(
                deal, player.player_id, market, trading_engine
            )
            profitable = received >= given * (1 + AI_ARBITRAGE_MIN_MARGIN) or (
                given == 0 and received > 0
            )
            if profitable:
                try:
                    trading_engine.accept_deal(
                        deal,
                        acceptor=target,
                        proposer=proposer,
                        acquired_tick=current_tick,
                        players=[player] + other_players,
                    )
                    actions.append(f"[AI] {player.name} accepted profitable deal #{deal.deal_id}")
                except Exception:
                    trading_engine.ledger.expire(deal.deal_id)
                    actions.append(f"[AI] {player.name} let stale deal #{deal.deal_id} expire")
            else:
                trading_engine.reject_deal(deal)
                actions.append(f"[AI] {player.name} rejected deal #{deal.deal_id}")
        return actions

    def _capture_visible_arbitrage(
        self, player: Player, market: Market, other_players: list[Player]
    ) -> list[str]:
        """Buy the cheapest ask and immediately fill richer bids when the spread is visible."""
        actions: list[str] = []
        for rtype in ResourceType:
            if rtype == ResourceType.FINANCE or rtype in NON_TRADABLE_RESOURCES:
                continue
            offer = market.best_offer(rtype)
            bid = market.best_bid(rtype)
            if offer is None or bid is None:
                continue
            if offer.seller_id == player.player_id or bid.buyer_id == player.player_id:
                continue
            if bid.price_per_unit < offer.price_per_unit * (1 + AI_ARBITRAGE_MIN_MARGIN):
                continue
            qty = min(offer.remaining, bid.remaining)
            if qty <= 0 or player.dollops < offer.price_per_unit * qty:
                continue
            try:
                players = [player] + other_players
                buy = trading_engine.execute_order_list(
                    player,
                    [{"side": "buy", "resource": rtype.value, "quantity": qty}],
                    players,
                )[0]
                bought = int(buy.get("quantity", 0))
                cost = abs(float(buy.get("total", 0.0)))
                sell = trading_engine.execute_order_list(
                    player,
                    [{"side": "sell", "resource": rtype.value, "quantity": bought}],
                    players,
                )[0]
                sold = int(sell.get("quantity", 0))
                paid = float(sell.get("total", 0.0))
            except Exception:
                continue
            if sold:
                actions.append(
                    f"[AI] {player.name} arbitraged {sold}x {rtype.value} "
                    f"for {paid - cost:.1f} Dp profit"
                )
        return actions

    def _ai_buy_vaccines_for_winter(
        self,
        player: Player,
        market: Market,
        trading_engine: TradingEngine,
        other_players: list[Player],
        season_name: str,
    ) -> list[str]:
        if player.is_human or season_name not in ("Autumn", FLU_SEASON):
            return []
        needed = vaccine_doses_needed(player.population)
        have = player.inventory.get(ResourceType.VACCINE)
        if have >= needed:
            return []
        target_qty = needed - have
        actions: list[str] = []
        offers = market.available_offers(ResourceType.VACCINE)
        available = sum(offer.remaining for offer in offers)
        if available > 0:
            fill_qty = min(target_qty, available)
            estimated = sum(
                offer.price_per_unit * take
                for offer, take in self._planned_offer_fills(offers, fill_qty)
            )
            if player.dollops >= estimated + AI_VACCINE_CASH_RESERVE:
                try:
                    order = trading_engine.execute_order_list(
                        player,
                        [{
                            "side": "buy",
                            "resource": ResourceType.VACCINE.value,
                            "quantity": fill_qty,
                        }],
                        [player] + other_players,
                    )[0]
                    bought = int(order.get("quantity", 0))
                    cost = abs(float(order.get("total", 0.0)))
                    if bought > 0:
                        target_qty -= bought
                        actions.append(
                            f"[AI] {player.name} stocked {bought}x Vaccine "
                            f"for Winter flu cover ({cost:.1f} Dp)"
                        )
                except Exception:
                    pass
        if target_qty > 0:
            bid_price = self._valuation_price(
                market, trading_engine, ResourceType.VACCINE
            )
            affordable = int(
                max(0.0, player.dollops - AI_VACCINE_CASH_RESERVE) // bid_price
            )
            bid_qty = min(target_qty, affordable)
            if bid_qty > 0:
                try:
                    market.post_bid(player, ResourceType.VACCINE, bid_price, bid_qty)
                    actions.append(
                        f"[AI] {player.name} bid for {bid_qty}x Vaccine "
                        f"ahead of Winter flu"
                    )
                except Exception:
                    pass
        return actions

    def _ai_buy_medical_supplies_for_qol(
        self,
        player: Player,
        market: Market,
        trading_engine: TradingEngine,
        other_players: list[Player],
    ) -> list[str]:
        if player.is_human:
            return []
        stockpile_target = ceil(max(0, player.population) / 10)
        nurse_target = player.workforce.count_profession("Nurse")
        target_qty = max(1, stockpile_target + nurse_target)
        have = player.inventory.get(ResourceType.MEDICAL_SUPPLIES)
        if have >= target_qty:
            return []
        target_qty -= have
        if target_qty <= 0:
            return []
        base_price = BASE_PRICES.get(ResourceType.MEDICAL_SUPPLIES.value, 0.0)
        max_price = base_price * 2
        offers = [
            offer for offer in market.available_offers(ResourceType.MEDICAL_SUPPLIES)
            if offer.seller_id != player.player_id and offer.price_per_unit <= max_price
        ]
        if not offers:
            return []
        bid_price = min(max_price, base_price)
        bid_qty = min(target_qty, sum(offer.remaining for offer in offers))
        if player.dollops < (bid_price * bid_qty) + AI_HEALTH_QOL_CASH_RESERVE:
            return []
        try:
            bid = market.post_bid(
                player, ResourceType.MEDICAL_SUPPLIES, bid_price, bid_qty
            )
        except Exception:
            return []
        bought = bid.quantity - bid.remaining
        cost = round(bought * bid_price, 2)
        if bought <= 0:
            return []
        return [
            f"[AI] {player.name} bought {bought}x MedicalSupplies "
            f"to improve QoL coverage ({cost:.1f} Dp)"
        ]

    def take_turn(
        self,
        player: Player,
        market: Market,
        other_players: list[Player],
        production_engine: ProductionEngine,
        trading_engine: TradingEngine,
        event_result: EventResult,
        season_name: str = "Spring",
        year: int = 0,
        season_index: int = 0,
        loan_ledger: LoanLedger | None = None,
        training_registry=None,
        cycle: BusinessCycleSnapshot | None = None,
        before_production: Callable[[], None] | None = None,
    ) -> list[str]:
        actions: list[str] = []

        if event_result.outage:
            actions.append(f"[AI] {player.name} — outage: {event_result.event_name}, skipping")
            return actions

        actions.extend(self._review_pending_deals(
            player,
            market,
            other_players,
            trading_engine,
            current_tick=year * 4 + season_index,
        ))

        is_manufacturer = any(r.name == "Manufacturer" for r in player.roles)
        chosen_line: str | None = None
        if is_manufacturer:
            chosen_line = self._choose_product_line(
                player, market, other_players,
                training_registry=training_registry,
                season_name=season_name,
            )

        actions.extend(
            self._ai_rollover_due_loans(
                player, loan_ledger, year, season_index, cycle=cycle
            )
        )
        actions.extend(
            self._ai_take_loan_if_short(
                player, market, other_players, loan_ledger, season_name,
                year, season_index, chosen_line, cycle=cycle,
            )
        )
        actions.extend(
            self._ai_buy_workplace_insurance(
                player, other_players, year, season_index
            )
        )
        actions.extend(
            self._ai_request_replacement_training(
                player, other_players, market, training_registry, year, season_index
            )
        )
        actions.extend(
            self._ai_invest_unclaimed_catalogue_item(
                player, year, season_index, other_players
            )
        )
        actions.extend(
            self._ai_buy_vaccines_for_winter(
                player, market, trading_engine, other_players, season_name
            )
        )
        actions.extend(
            self._ai_buy_medical_supplies_for_qol(
                player, market, trading_engine, other_players
            )
        )

        inputs_needed = self._inputs_for_ai_purchase(
            player,
            season_name,
            chosen_line,
            banker_office_goods=self._banker_has_active_book(
                player, other_players, loan_ledger, year, season_index,
            ),
        )
        for rtype, qty_needed in inputs_needed.items():
            if rtype == ResourceType.FINANCE or rtype in NON_TRADABLE_RESOURCES:
                continue
            target_runs = (
                1
                if rtype in EQUIPMENT_RESOURCE_CAPITAL or rtype == ResourceType.SPARES
                else AI_EQUIPMENT_INPUT_RUNS
                if rtype in AI_EQUIPMENT_INPUTS else self.target_production_runs
            )
            target_qty = qty_needed * target_runs
            if rtype == ResourceType.OIL:
                target_qty += player.energy_floor_oil_required(CAPITAL_CATALOGUE)
            elif rtype == ResourceType.EXPERTISE:
                production_need = player.all_required_inputs(
                    season_name, chosen_line
                ).get(ResourceType.EXPERTISE, 0)
                target_qty = (
                    production_need * self.target_production_runs
                    + self._ce_expertise_shortfall(player)
                )
            elif (
                rtype == ResourceType.GOODS
                and any(role.name == "Banker" for role in player.roles)
            ):
                target_qty = qty_needed
            have = player.inventory.get(rtype)
            if have >= target_qty:
                continue
            buy_qty = target_qty - have
            offers = market.available_offers(rtype)
            avail = sum(o.remaining for o in offers)
            if avail > 0 and offers:
                fill_qty = min(buy_qty, avail)
                est_cost = sum(
                    offer.price_per_unit * take
                    for offer, take in self._planned_offer_fills(offers, fill_qty)
                )
                if player.dollops >= est_cost:
                    try:
                        order = trading_engine.execute_order_list(
                            player,
                            [{"side": "buy", "resource": rtype.value, "quantity": fill_qty}],
                            [player] + other_players,
                        )[0]
                        bought = int(order.get("quantity", 0))
                        cost = abs(float(order.get("total", 0.0)))
                        actions.append(
                            f"[AI] {player.name} bought {bought}x {rtype.value} "
                            f"for {cost:.1f} Dp"
                        )
                        buy_qty -= bought
                    except Exception:
                        pass
            if buy_qty > 0 and rtype == ResourceType.OIL:
                floor_shortfall = max(
                    0,
                    player.energy_floor_oil_required(CAPITAL_CATALOGUE)
                    - player.inventory.get(ResourceType.OIL),
                )
                fill_qty = min(
                    buy_qty,
                    floor_shortfall,
                    market.market_maker_buy_depth(rtype),
                )
                if fill_qty > 0:
                    ask = market.market_maker_ask(rtype)
                    affordable_qty = min(fill_qty, int(player.dollops // ask))
                    if affordable_qty > 0:
                        try:
                            market.post_supply(rtype, affordable_qty)
                            paid = market.execute_buy(player, rtype, affordable_qty)
                            actions.append(
                                f"[AI] {player.name} imported {affordable_qty}x Oil "
                                f"for {paid:.1f} Dp"
                            )
                            buy_qty -= affordable_qty
                        except Exception:
                            pass
            if buy_qty > 0:
                bid_price = self._valuation_price(market, trading_engine, rtype)
                affordable_qty = min(buy_qty, int(player.dollops // bid_price))
                if affordable_qty > 0:
                    try:
                        market.post_bid(player, rtype, bid_price, affordable_qty)
                        actions.append(
                            f"[AI] {player.name} bid for {affordable_qty}x {rtype.value} "
                            f"at {bid_price:.1f} Dp/unit"
                        )
                    except Exception:
                        pass

        if before_production is not None:
            before_production()

        produced_totals: dict[ResourceType, int] = {}
        missing: dict[ResourceType, int] = {}
        selected_farmer_output = self._farmer_visible_human_demand_output(
            player, market, other_players, production_engine, event_result, season_name
        )
        if selected_farmer_output is not None:
            output, qty = selected_farmer_output
            produced = production_engine.produce_product(
                player, event_result, season_name, "Farmer", output, qty
            )
            if produced:
                for rtype, qty in produced.items():
                    produced_totals[rtype] = produced_totals.get(rtype, 0) + qty
        else:
            for _ in range(self.target_production_runs):
                can, missing = production_engine.can_produce(
                    player, event_result, season_name, chosen_line
                )
                if not can:
                    break
                produced = production_engine.produce(player, event_result, season_name, chosen_line)
                if produced:
                    for rtype, qty in produced.items():
                        produced_totals[rtype] = produced_totals.get(rtype, 0) + qty
        if produced_totals:
            if is_manufacturer:
                supply_memory = getattr(player, "ai_equipment_supply_memory", {})
                for rtype, qty in produced_totals.items():
                    if rtype in AI_EQUIPMENT_INPUTS:
                        supply_memory[rtype.value] = supply_memory.get(rtype.value, 0) + qty
                player.ai_equipment_supply_memory = supply_memory
            line_tag = f" [{MANUFACTURER_PRODUCT_LINES[chosen_line]['desc']}]" if chosen_line else ""
            summary = ", ".join(f"{qty}x {r.value}" for r, qty in produced_totals.items())
            actions.append(f"[AI] {player.name} produced{line_tag}: {summary}")
        elif missing:
            if is_manufacturer and not any(
                self._manufacturer_line_feasible(player, line_key)
                for line_key in MANUFACTURER_PRODUCT_LINES
            ):
                actions.append(
                    f"[AI] {player.name} Manufacturer idle — out of inputs for all product lines"
                )
            else:
                missing_str = ", ".join(f"{qty}x {r.value}" for r, qty in missing.items())
                actions.append(f"[AI] {player.name} cannot produce — missing: {missing_str}")

        if any(r.name == "Banker" for r in player.roles):
            actions.extend(
                self._ai_offer_insurance(player, other_players, season_name, year, season_index)
            )
            actions.extend(
                self._ai_offer_loans(
                    player, other_players, market, loan_ledger,
                    season_name, year, season_index, cycle=cycle,
                )
            )

        reserve_inputs = player.all_required_inputs(season_name, chosen_line)
        oil_production_reserve = reserve_inputs.get(ResourceType.OIL, 0) * self.target_production_runs
        reserve_inputs[ResourceType.OIL] = max(
            reserve_inputs.get(ResourceType.OIL, 0),
            oil_production_reserve + player.energy_floor_oil_required(CAPITAL_CATALOGUE),
        )
        listable_resources = set(player.all_produced_resources()) | set(produced_totals)
        if is_manufacturer:
            listable_resources.add(ResourceType.SPARES)
        for rtype in listable_resources:
            if rtype == ResourceType.FINANCE or rtype in NON_TRADABLE_RESOURCES:
                continue
            if rtype in AI_LIST_ONLY_WITH_BID and market.best_bid(rtype) is None:
                continue
            qty = max(0, player.inventory.get(rtype) - reserve_inputs.get(rtype, 0))
            if rtype == ResourceType.VACCINE:
                qty = max(0, qty - vaccine_doses_needed(player.population))
            if (
                is_manufacturer
                and rtype == ResourceType.REAGENTS
                and getattr(player, "ai_product_line_human_demand", False)
            ):
                qty = min(qty, 1)
            if qty <= 0:
                continue
            price = round(market.current_price(rtype) * AI_OFFER_MARKUP, 2)
            base = BASE_PRICES.get(rtype.value, price)
            if price >= base * 0.8:
                try:
                    market.post_offer(player, rtype, price, qty)
                    actions.append(
                        f"[AI] {player.name} listed {qty}x {rtype.value} "
                        f"at {price:.1f} Dp/unit"
                    )
                except Exception:
                    pass

        actions.extend(self._capture_visible_arbitrage(player, market, other_players))
        return actions

    def _planned_offer_fills(self, offers, qty: int):
        remaining = qty
        for offer in offers:
            if remaining <= 0:
                break
            take = min(remaining, offer.remaining)
            if take > 0:
                yield offer, take
                remaining -= take
