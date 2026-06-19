import pytest

from island_traders.models.deal import DealLedger, DealStatus
from island_traders.models.resource import ResourceType


def test_return_to_proposer_flips_awaiting_party_and_updates_terms():
    ledger = DealLedger()
    deal = ledger.create_proposal(
        proposer_id=1,
        target_id=2,
        offer_resource=ResourceType.FOOD,
        offer_qty=2,
        request_resource=ResourceType.OIL,
        request_qty=1,
    )

    returned = ledger.return_to_proposer(
        deal.deal_id,
        responder_id=2,
        offer_resource=ResourceType.FOOD,
        offer_qty=1,
        request_resource=ResourceType.OIL,
        request_qty=2,
        gold_sweetener=-5.0,
        message="Need more Oil.",
    )

    assert returned.status == DealStatus.RETURNED
    assert returned.awaiting_id == 1
    assert returned.offer_qty == 1
    assert returned.request_qty == 2
    assert returned.gold_sweetener == -5.0
    assert returned.message == "Need more Oil."
    assert returned.last_response_by_id == 2


def test_reject_is_terminal_for_returned_deal():
    ledger = DealLedger()
    deal = ledger.create_proposal(
        proposer_id=1,
        target_id=2,
        offer_resource=ResourceType.FOOD,
        offer_qty=2,
        request_resource=None,
        request_qty=0,
    )
    ledger.return_to_proposer(
        deal.deal_id,
        responder_id=2,
        offer_resource=ResourceType.FOOD,
        offer_qty=1,
        request_resource=None,
        request_qty=0,
    )
    ledger.reject(deal.deal_id)

    assert deal.status == DealStatus.REJECTED
    assert deal.awaiting_id is None
    with pytest.raises(ValueError):
        ledger.return_to_proposer(
            deal.deal_id,
            responder_id=1,
            offer_resource=ResourceType.FOOD,
            offer_qty=1,
            request_resource=None,
            request_qty=0,
        )


def test_expire_for_player_sweeps_pending_and_returned_deals():
    ledger = DealLedger()
    pending = ledger.create_proposal(1, 2, ResourceType.FOOD, 1, None, 0)
    returned = ledger.create_proposal(3, 2, ResourceType.OIL, 1, None, 0)
    ledger.return_to_proposer(
        returned.deal_id,
        responder_id=2,
        offer_resource=ResourceType.OIL,
        offer_qty=1,
        request_resource=None,
        request_qty=0,
    )

    expired = ledger.expire_for_player(2)

    assert expired == [pending]
    assert pending.status == DealStatus.EXPIRED
    assert returned.status == DealStatus.RETURNED
