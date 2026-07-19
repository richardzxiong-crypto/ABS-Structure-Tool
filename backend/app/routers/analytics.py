from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from absengine.analytics.breakeven import solve_breakevens
from absengine.analytics.matrix import price_yield_table, sensitivity_matrix
from absengine.library import DealLibrary
from absengine.runner import UnsupportedFeatureError

from ..deps import get_library

router = APIRouter(prefix="/api", tags=["analytics"])


class BreakevenBody(BaseModel):
    scenario: str | None = None


class MatrixBody(BaseModel):
    scenario: str | None = None
    prepay_mults: list[float] | None = None
    loss_mults: list[float] | None = None


class PriceYieldBody(BaseModel):
    scenario: str | None = None
    prices: list[float] | None = None


def _load(lib: DealLibrary, deal_id: str):
    try:
        return lib.load(deal_id)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))


@router.post("/deals/{deal_id}/analytics/breakeven")
def breakeven(deal_id: str, body: BreakevenBody | None = None,
              lib: DealLibrary = Depends(get_library)) -> dict:
    deal = _load(lib, deal_id)
    body = body or BreakevenBody()
    try:
        return solve_breakevens(deal, body.scenario)
    except UnsupportedFeatureError as e:
        raise HTTPException(422, str(e))
    except KeyError as e:
        raise HTTPException(404, str(e))


@router.post("/deals/{deal_id}/analytics/matrix")
def matrix(deal_id: str, body: MatrixBody | None = None,
           lib: DealLibrary = Depends(get_library)) -> dict:
    deal = _load(lib, deal_id)
    body = body or MatrixBody()
    try:
        return sensitivity_matrix(deal, body.scenario, body.prepay_mults, body.loss_mults)
    except UnsupportedFeatureError as e:
        raise HTTPException(422, str(e))
    except KeyError as e:
        raise HTTPException(404, str(e))


@router.post("/deals/{deal_id}/analytics/price-yield")
def price_yield(deal_id: str, body: PriceYieldBody | None = None,
                lib: DealLibrary = Depends(get_library)) -> dict:
    deal = _load(lib, deal_id)
    body = body or PriceYieldBody()
    try:
        return price_yield_table(deal, body.scenario, body.prices)
    except UnsupportedFeatureError as e:
        raise HTTPException(422, str(e))
    except KeyError as e:
        raise HTTPException(404, str(e))
