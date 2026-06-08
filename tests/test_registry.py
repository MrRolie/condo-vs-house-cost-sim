import pytest
from mcp_server import registry
from hde.config import load_config_dict


@pytest.fixture(autouse=True)
def clean_registry():
    registry.clear()
    yield
    registry.clear()


def _spec(**overrides):
    config = {
        "years": 20,
        "discount_rate": 0.03,
        "condo": {"monthly_fee": 500},
        "house": {"initial_value": 400_000},
    }
    config.update(overrides)
    return load_config_dict(config)


def test_define_and_get():
    spec = _spec()
    registry.define("s1", {"years": 20}, spec)
    entry = registry.get("s1")
    assert entry.name == "s1"
    assert entry.raw_config == {"years": 20}
    assert entry.spec is spec
    assert entry.det_result is None
    assert entry.mc_result is None


def test_define_overwrites_silently():
    spec_a = _spec(condo={"monthly_fee": 500})
    spec_b = _spec(condo={"monthly_fee": 900})
    registry.define("s1", {}, spec_a)
    registry.define("s1", {}, spec_b)
    assert registry.get("s1").spec is spec_b


def test_get_missing_raises_key_error():
    with pytest.raises(KeyError):
        registry.get("nonexistent")


def test_all_entries_empty():
    assert registry.all_entries() == []


def test_all_entries_lists_names_and_result_flags():
    registry.define("a", {}, _spec())
    registry.define("b", {}, _spec())
    entries = registry.all_entries()
    assert len(entries) == 2
    assert {e["name"] for e in entries} == {"a", "b"}
    for e in entries:
        assert e["has_det_result"] is False
        assert e["has_mc_result"] is False


def test_remove_existing():
    registry.define("s1", {}, _spec())
    registry.remove("s1")
    with pytest.raises(KeyError):
        registry.get("s1")


def test_remove_missing_raises_key_error():
    with pytest.raises(KeyError):
        registry.remove("nonexistent")


def test_store_det_result():
    registry.define("s1", {}, _spec())
    sentinel = object()
    registry.store_results("s1", det_result=sentinel)
    entry = registry.get("s1")
    assert entry.det_result is sentinel
    assert entry.mc_result is None


def test_store_mc_result():
    registry.define("s1", {}, _spec())
    sentinel = object()
    registry.store_results("s1", mc_result=sentinel)
    entry = registry.get("s1")
    assert entry.mc_result is sentinel
    assert entry.det_result is None


def test_all_entries_reflects_result_flags():
    registry.define("s1", {}, _spec())
    registry.store_results("s1", det_result=object())
    entries = registry.all_entries()
    assert entries[0]["has_det_result"] is True
    assert entries[0]["has_mc_result"] is False


def test_clear_empties_registry():
    registry.define("s1", {}, _spec())
    registry.clear()
    assert registry.all_entries() == []
