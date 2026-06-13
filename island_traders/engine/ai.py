from __future__ import annotations
from math import ceil
from ..models.player import EQUIPMENT_RESOURCE_CAPITAL, Player
from ..models.market import Market
from ..models.resource import ResourceType
from ..models.deal import DealProposal, DealStatus
from ..engine.events import EventResult
from ..engine.production import ProductionEngine
from ..engine.trading import TradingEngine
from ..engine.revenue import revenue_opportunities
from ..models.insurance import InsurancePolicy
from ..models.loan import LoanLedger, LoanStatus, banker_quote_rate, posted_funding_rates
from ..models.profession import Profession
from ..models.equity import UNISSUED_HOLDER, fair_value, share_price
from ..constants import (
    BASE_PRICES, MANUFACTURER_PRODUCT_LINES, PRODUCER_PRODUCTIVITY_MULTIPLIER,
    PRODUCTION_INPUTS,
    WORKPLACE_RISK, INSURANCE_BASE_PREMIUM, INSURANCE_DURATION_SEASONS,
    MBA_RESERVE_RATIO_BASE, MBA_RESERVE_RATIO_QUALIFIED,
    MBA_QUALIFIED_THRESHOLD, ACTUARIAL_EVALUATION_COST,
)
from ..constants_capacity import CAPITAL_CATALOGUE
from ..models.capacity import items_for_role

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
        funding_rate = posted_funding_rates(year, season_index)[term_years]
        rate = banker_quote_rate(
            borrower, loan_ledger, principal, term_years, year, season_index
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
                banker, borrower, principal, loan_ledger, year, season_index
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
                        banker, player, principal, loan_ledger, year, season_index
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
        available_cash = player.personal_cash - AI_PERSONAL_CASH_RESERVE
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
        player.personal_cash = round(player.personal_cash - cost, 1)
        player.dollops = round(player.dollops + cost, 1)
        owner_key = str(player.player_id)
        player.cap_table.transfer(UNISSUED_HOLDER, owner_key, shares)
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
                player, loan_ledger, loan.repayment_amount, 1, year, season_index
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
        if player.dollops <= item.cost * 2:
            return []
        player.dollops -= item.cost
        current_tick = year * 4 + season_index
        player.add_capital(item.item_id, 1, acquired_tick=current_tick)
        return [
            f"[AI] {player.name} invested {item.cost:.0f} Dp in {item.name}"
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
            for role in target.roles:
                risk = WORKPLACE_RISK.get(role.name, {})
                if not risk.get("injury_rate") and not risk.get("fatality_rate"):
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
        has_visible_bid = any(
            market.best_bid(ResourceType(line["output"])) is not None
            for line in MANUFACTURER_PRODUCT_LINES.values()
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
        feasible = [
            line_key for line_key in MANUFACTURER_PRODUCT_LINES
            if self._manufacturer_line_feasible(player, line_key)
        ]
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
        bid_lines = [
            line_key for line_key, line in MANUFACTURER_PRODUCT_LINES.items()
            if market.best_bid(ResourceType(line["output"])) is not None
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
        return all(
            player.inventory.get(ResourceType(resource)) >= qty
            for resource, qty in line["inputs"].items()
        )

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
        return inputs

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

    def _deal_value_for_acceptor(
        self, deal: DealProposal, market: Market, trading_engine: TradingEngine
    ) -> tuple[float, float]:
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
            if proposer is None:
                trading_engine.ledger.expire(deal.deal_id)
                actions.append(f"[AI] {player.name} let stale deal #{deal.deal_id} expire")
                continue
            received, given = self._deal_value_for_acceptor(deal, market, trading_engine)
            profitable = received >= given * (1 + AI_ARBITRAGE_MIN_MARGIN) or (
                given == 0 and received > 0
            )
            if profitable:
                try:
                    trading_engine.accept_deal(
                        deal,
                        acceptor=player,
                        proposer=proposer,
                        acquired_tick=current_tick,
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
            if rtype == ResourceType.FINANCE:
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
                cost, bought = market.buy_from_offers(player, rtype, qty)
                paid, sold = market.sell_to_bids(player, rtype, bought, other_players)
            except Exception:
                continue
            if sold:
                actions.append(
                    f"[AI] {player.name} arbitraged {sold}x {rtype.value} "
                    f"for {paid - cost:.1f} Dp profit"
                )
        return actions

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
            self._ai_rollover_due_loans(player, loan_ledger, year, season_index)
        )
        actions.extend(
            self._ai_take_loan_if_short(
                player, market, other_players, loan_ledger, season_name,
                year, season_index, chosen_line,
            )
        )
        actions.extend(
            self._ai_invest_unclaimed_catalogue_item(player, year, season_index)
        )

        inputs_needed = self._inputs_for_ai_purchase(player, season_name, chosen_line)
        for rtype, qty_needed in inputs_needed.items():
            if rtype == ResourceType.FINANCE:
                continue
            target_runs = (
                1
                if rtype in EQUIPMENT_RESOURCE_CAPITAL
                else AI_EQUIPMENT_INPUT_RUNS
                if rtype in AI_EQUIPMENT_INPUTS else self.target_production_runs
            )
            target_qty = qty_needed * target_runs
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
                        cost, bought = market.buy_from_offers(player, rtype, fill_qty)
                        actions.append(
                            f"[AI] {player.name} bought {bought}x {rtype.value} "
                            f"for {cost:.1f} Dp"
                        )
                        buy_qty -= bought
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
                    season_name, year, season_index,
                )
            )

        reserve_inputs = player.all_required_inputs(season_name, chosen_line)
        listable_resources = set(player.all_produced_resources()) | set(produced_totals)
        for rtype in listable_resources:
            if rtype == ResourceType.FINANCE:
                continue
            if rtype in AI_LIST_ONLY_WITH_BID and market.best_bid(rtype) is None:
                continue
            qty = max(0, player.inventory.get(rtype) - reserve_inputs.get(rtype, 0))
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
