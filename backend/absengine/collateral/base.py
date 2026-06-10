from __future__ import annotations

from typing import Protocol

from ..models.collateral import CollateralPool
from ..models.scenario import Scenario
from ..registry import Registry
from .result import CollateralCashflows


class AssetModel(Protocol):
    """A registered asset-class projection model."""

    def project(
        self, pool: CollateralPool, scenario: Scenario, num_periods: int
    ) -> CollateralCashflows: ...


ASSET_REGISTRY = Registry("asset_classes")


def project_pool(pool: CollateralPool, scenario: Scenario, num_periods: int) -> CollateralCashflows:
    handler = ASSET_REGISTRY.handler_for(_Keyed(pool.asset_class))
    return handler.project(pool, scenario, num_periods)


class _Keyed:
    def __init__(self, type_key: str):
        self.type = type_key
