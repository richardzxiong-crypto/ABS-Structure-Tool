from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ValidationError

from absengine.library import DealLibrary
from absengine.models.deal import Deal
from absengine.runner import UnsupportedFeatureError, check_phase1_support

from ..deps import get_library

router = APIRouter(prefix="/api", tags=["deals"])


@router.get("/deals")
def list_deals(lib: DealLibrary = Depends(get_library)) -> list[dict]:
    return lib.list()


@router.post("/deals", status_code=201)
def create_deal(deal: Deal, lib: DealLibrary = Depends(get_library)) -> dict:
    try:
        lib.load(deal.id)
    except FileNotFoundError:
        lib.save(deal)
        return {"id": deal.id}
    raise HTTPException(409, f"deal {deal.id!r} already exists")


@router.get("/deals/{deal_id}")
def get_deal(deal_id: str, lib: DealLibrary = Depends(get_library)) -> Deal:
    try:
        return lib.load(deal_id)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))


@router.put("/deals/{deal_id}")
def update_deal(deal_id: str, deal: Deal, lib: DealLibrary = Depends(get_library)) -> dict:
    if deal.id != deal_id:
        raise HTTPException(400, "deal id in body does not match URL")
    lib.save(deal)
    return {"id": deal.id}


@router.delete("/deals/{deal_id}")
def delete_deal(deal_id: str, lib: DealLibrary = Depends(get_library)) -> dict:
    try:
        lib.delete(deal_id)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    return {"deleted": deal_id}


class CloneBody(BaseModel):
    new_id: str
    new_name: str | None = None


@router.post("/deals/{deal_id}/clone", status_code=201)
def clone_deal(deal_id: str, body: CloneBody, lib: DealLibrary = Depends(get_library)) -> dict:
    try:
        cloned = lib.clone(deal_id, body.new_id, body.new_name)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except FileExistsError as e:
        raise HTTPException(409, str(e))
    return {"id": cloned.id}


@router.get("/deals/{deal_id}/versions")
def deal_versions(deal_id: str, lib: DealLibrary = Depends(get_library)) -> list[str]:
    return lib.versions(deal_id)


@router.get("/templates")
def list_templates(lib: DealLibrary = Depends(get_library)) -> list[dict]:
    return lib.templates()


@router.get("/templates/{template}")
def get_template(template: str, lib: DealLibrary = Depends(get_library)) -> Deal:
    try:
        return lib.load_template(template)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))


@router.post("/deals/validate")
def validate_deal(payload: dict) -> dict:
    """Structural validation + Phase-1 capability check, without saving."""
    try:
        deal = Deal.model_validate(payload)
    except ValidationError as e:
        return {"valid": False, "errors": [str(err["msg"]) for err in e.errors()]}
    try:
        check_phase1_support(deal)
    except UnsupportedFeatureError as e:
        return {"valid": True, "runnable": False, "errors": [str(e)]}
    return {"valid": True, "runnable": True, "errors": []}
