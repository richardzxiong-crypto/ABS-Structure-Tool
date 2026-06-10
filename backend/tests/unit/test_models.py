import pytest
from pydantic import ValidationError

from absengine.models.deal import Deal
from absengine.runner import UnsupportedFeatureError, check_phase1_support
from absengine.waterfall.steps import STEP_REGISTRY
from tests.conftest import make_deal


def test_valid_deal_roundtrips(deal):
    data = deal.model_dump()
    assert Deal.model_validate(data) == deal


def test_unknown_step_target_rejected():
    with pytest.raises(ValidationError, match="unknown targets"):
        deal = make_deal()
        cfg = deal.model_dump()
        cfg["waterfall"]["waterfalls"][0]["steps"][1]["targets"] = ["Z"]
        Deal.model_validate(cfg)


def test_unknown_source_rejected():
    with pytest.raises(ValidationError, match="unknown source"):
        cfg = make_deal().model_dump()
        cfg["waterfall"]["waterfalls"][0]["steps"][0]["source"] = "bogus"
        Deal.model_validate(cfg)


def test_combined_mode_rejects_split_sources():
    with pytest.raises(ValidationError, match="combined-mode"):
        cfg = make_deal().model_dump()
        cfg["waterfall"]["mode"] = "combined"
        Deal.model_validate(cfg)


def test_unknown_fee_rejected():
    with pytest.raises(ValidationError, match="unknown fees"):
        cfg = make_deal().model_dump()
        cfg["waterfall"]["waterfalls"][0]["steps"][0]["fees"] = ["nope"]
        Deal.model_validate(cfg)


def test_tree_must_cover_all_classes():
    with pytest.raises(ValidationError, match="missing from allocation tree"):
        cfg = make_deal().model_dump()
        cfg["structure"]["allocation_tree"]["children"].pop()
        cfg["waterfall"]["waterfalls"][0]["steps"][1]["targets"] = ["A"]
        cfg["waterfall"]["waterfalls"][1]["steps"][0]["targets"] = ["A"]
        Deal.model_validate(cfg)


def test_phase1_rejects_floating_coupon():
    cfg = make_deal().model_dump()
    cfg["structure"]["classes"][0]["coupon"] = {"type": "floating", "index": "SOFR", "margin": 0.01}
    deal = Deal.model_validate(cfg)
    with pytest.raises(UnsupportedFeatureError, match="floating"):
        check_phase1_support(deal)


def test_phase1_rejects_priority_pda():
    cfg = make_deal().model_dump()
    cfg["waterfall"]["waterfalls"][1]["steps"][0]["amount_rule"] = "priority_pda"
    deal = Deal.model_validate(cfg)
    with pytest.raises(UnsupportedFeatureError, match="priority_pda"):
        check_phase1_support(deal)


def test_every_step_type_has_a_handler():
    """Import-order / registry-coverage test: each AnyStep union member is
    registered and vice versa."""
    from typing import get_args

    from absengine.models.waterfall import AnyStep

    union_types = {m.model_fields["type"].default for m in get_args(get_args(AnyStep)[0])}
    registered = set(STEP_REGISTRY.type_keys)
    # fund_reserve is modeled but lands in Phase 2 (no handler yet)
    assert registered == union_types - {"fund_reserve"}
