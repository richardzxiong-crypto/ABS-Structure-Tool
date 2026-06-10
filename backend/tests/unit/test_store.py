import pytest

from absengine.library import DealLibrary
from tests.conftest import make_deal


def test_save_load_roundtrip(tmp_path):
    lib = DealLibrary(tmp_path)
    deal = make_deal()
    lib.save(deal)
    assert lib.load(deal.id) == deal
    assert [d["id"] for d in lib.list()] == [deal.id]


def test_version_snapshot_on_overwrite(tmp_path):
    lib = DealLibrary(tmp_path)
    deal = make_deal()
    lib.save(deal)
    assert lib.versions(deal.id) == []
    deal2 = deal.model_copy(update={"name": "renamed"})
    lib.save(deal2)
    assert len(lib.versions(deal.id)) == 1
    assert lib.load(deal.id).name == "renamed"


def test_clone(tmp_path):
    lib = DealLibrary(tmp_path)
    lib.save(make_deal())
    cloned = lib.clone("test-deal", "test-deal-2")
    assert cloned.id == "test-deal-2"
    assert lib.load("test-deal-2").structure == lib.load("test-deal").structure
    with pytest.raises(FileExistsError):
        lib.clone("test-deal", "test-deal-2")


def test_delete(tmp_path):
    lib = DealLibrary(tmp_path)
    lib.save(make_deal())
    lib.delete("test-deal")
    assert lib.list() == []
    with pytest.raises(FileNotFoundError):
        lib.load("test-deal")


def test_invalid_id_rejected(tmp_path):
    lib = DealLibrary(tmp_path)
    with pytest.raises(ValueError, match="invalid deal id"):
        lib.load("../../etc/passwd")
