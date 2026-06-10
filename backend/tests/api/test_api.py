import pytest
from fastapi.testclient import TestClient

from absengine.library import DealLibrary
from app.deps import get_library
from app.main import app
from tests.conftest import make_deal


@pytest.fixture
def client(tmp_path):
    app.dependency_overrides[get_library] = lambda: DealLibrary(tmp_path)
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_crud_roundtrip(client):
    payload = make_deal().model_dump(mode="json")
    assert client.post("/api/deals", json=payload).status_code == 201
    assert client.post("/api/deals", json=payload).status_code == 409

    deals = client.get("/api/deals").json()
    assert [d["id"] for d in deals] == ["test-deal"]

    got = client.get("/api/deals/test-deal").json()
    assert got["structure"]["classes"][0]["id"] == "A"

    payload["name"] = "renamed"
    assert client.put("/api/deals/test-deal", json=payload).status_code == 200
    assert client.get("/api/deals/test-deal").json()["name"] == "renamed"
    assert client.get("/api/deals/test-deal/versions").json() != []

    r = client.post("/api/deals/test-deal/clone", json={"new_id": "copy1"})
    assert r.status_code == 201

    assert client.delete("/api/deals/test-deal").status_code == 200
    assert client.get("/api/deals/test-deal").status_code == 404


def test_run_endpoint(client):
    client.post("/api/deals", json=make_deal().model_dump(mode="json"))
    r = client.post("/api/deals/test-deal/run", json={"scenario": "base"})
    assert r.status_code == 200
    body = r.json()
    assert body["num_periods"] == 12
    assert len(body["collateral"]["end_trust"]) == 12
    assert "A" in body["metrics"]["bonds"]
    # inline scenario override
    r2 = client.post(
        "/api/deals/test-deal/run",
        json={"inline_scenario": {"name": "hot", "prepay": {"speed": {"type": "scalar", "value": 0.5}}}},
    )
    assert r2.status_code == 200
    assert r2.json()["scenario_name"] == "hot"


def test_validate_endpoint(client):
    payload = make_deal().model_dump(mode="json")
    r = client.post("/api/deals/validate", json=payload).json()
    assert r == {"valid": True, "runnable": True, "errors": []}

    payload["waterfall"]["waterfalls"][1]["steps"][0]["amount_rule"] = "turbo"
    r = client.post("/api/deals/validate", json=payload).json()
    assert r["valid"] is True and r["runnable"] is False

    payload["waterfall"]["waterfalls"][1]["steps"][0]["amount_rule"] = "bogus"
    r = client.post("/api/deals/validate", json=payload).json()
    assert r["valid"] is False


def test_meta_endpoints(client):
    types = client.get("/api/meta/step-types").json()["types"]
    assert "pay_principal" in types and "pay_interest" in types
    assert "amortizing_loan" in client.get("/api/meta/asset-classes").json()["types"]
