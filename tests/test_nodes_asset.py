import pytest
from nodes import nodes_asset


def test_build_asset_uri():
    assert nodes_asset.build_asset_uri("asset-2026-abc") == "asset://asset-2026-abc"


def test_build_asset_uri_passthrough():
    assert nodes_asset.build_asset_uri("asset://asset-2026-abc") == "asset://asset-2026-abc"


def test_build_asset_uri_rejects_empty():
    with pytest.raises(ValueError):
        nodes_asset.build_asset_uri("")
