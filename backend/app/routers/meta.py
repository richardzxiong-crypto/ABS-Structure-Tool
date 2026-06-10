from fastapi import APIRouter

from absengine.collateral import ASSET_REGISTRY
from absengine.triggers import TRIGGER_REGISTRY
from absengine.waterfall.steps import STEP_REGISTRY

router = APIRouter(prefix="/api/meta", tags=["meta"])


@router.get("/step-types")
def step_types() -> dict:
    return {"types": STEP_REGISTRY.type_keys, "schemas": STEP_REGISTRY.json_schemas()}


@router.get("/trigger-types")
def trigger_types() -> dict:
    return {"types": TRIGGER_REGISTRY.type_keys, "schemas": TRIGGER_REGISTRY.json_schemas()}


@router.get("/asset-classes")
def asset_classes() -> dict:
    return {"types": ASSET_REGISTRY.type_keys}
