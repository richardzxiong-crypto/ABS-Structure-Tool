import pytest

from absengine.models.deal import Deal


def make_deal(**overrides) -> Deal:
    """The canonical 2-tranche sequential test deal (golden test 6 base)."""
    cfg = {
        "id": "test-deal",
        "name": "Test Deal",
        "num_periods": 12,
        "collateral": {
            "replines": [
                {"id": "R1", "balance": 100.0, "gross_rate": 0.08,
                 "original_term": 12, "remaining_term": 12}
            ],
        },
        "structure": {
            "classes": [
                {"id": "A", "balance": 80.0, "coupon": {"type": "fixed", "rate": 0.05}},
                {"id": "B", "balance": 20.0, "coupon": {"type": "fixed", "rate": 0.07}},
            ],
            "allocation_tree": {
                "type": "group", "name": "root", "mode": "sequential",
                "children": [
                    {"type": "class", "class_id": "A"},
                    {"type": "class", "class_id": "B"},
                ],
            },
        },
        "fees": [{"name": "trustee", "rate": 0.0025}],
        "waterfall": {
            "mode": "split",
            "waterfalls": [
                {"name": "interest", "steps": [
                    {"type": "pay_fees", "id": "i1", "source": "interest_collections",
                     "fees": ["trustee"]},
                    {"type": "pay_interest", "id": "i2", "source": "interest_collections",
                     "targets": ["A", "B"]},
                ]},
                {"name": "principal", "steps": [
                    {"type": "pay_principal", "id": "p1", "source": "principal_collections",
                     "targets": ["A", "B"]},
                    {"type": "release_residual", "id": "p2", "source": "principal_collections"},
                    {"type": "release_residual", "id": "p3", "source": "interest_collections"},
                ]},
            ],
        },
        "scenarios": [{
            "name": "base",
            "prepay": {"speed": {"type": "scalar", "value": 0.05}},
            "loss": {
                "defaults": {"type": "cdr", "cdr": {"type": "scalar", "value": 0.01}},
                "severity": {"type": "scalar", "value": 0.5},
                "charge_off_lag": 1,
                "recovery_lag": 2,
            },
        }],
    }
    cfg.update(overrides)
    return Deal.model_validate(cfg)


@pytest.fixture
def deal() -> Deal:
    return make_deal()
