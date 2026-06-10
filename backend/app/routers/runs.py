from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from absengine.library import DealLibrary
from absengine.models.scenario import Scenario
from absengine.runner import UnsupportedFeatureError, run_deal

from ..deps import get_library

router = APIRouter(prefix="/api", tags=["runs"])


class RunBody(BaseModel):
    scenario: str | None = None
    inline_scenario: Scenario | None = None


@router.post("/deals/{deal_id}/run")
def run(deal_id: str, body: RunBody | None = None, lib: DealLibrary = Depends(get_library)) -> dict:
    try:
        deal = lib.load(deal_id)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    body = body or RunBody()
    scenario = body.inline_scenario if body.inline_scenario is not None else body.scenario
    try:
        result = run_deal(deal, scenario)
    except UnsupportedFeatureError as e:
        raise HTTPException(422, str(e))
    except KeyError as e:
        raise HTTPException(404, str(e))
    return result.to_json_dict()
