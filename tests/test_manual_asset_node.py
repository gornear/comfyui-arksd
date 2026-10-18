"""The standalone node for externally authorized asset ids."""

import pytest

from nodes import nodes_asset


def _execute(asset_id):
    return nodes_asset.ArkSDAssetManual.execute(asset_id=asset_id)


def test_outputs_asset_uri():
    result = _execute("asset-20261017202759-8x5qv")
    assert result.args[0] == "asset://asset-20261017202759-8x5qv"


def test_accepts_full_uri():
    result = _execute("asset://asset-20261017202759-8x5qv")
    assert result.args[0] == "asset://asset-20261017202759-8x5qv"


def test_strips_whitespace():
    result = _execute("  asset-2026-x  ")
    assert result.args[0] == "asset://asset-2026-x"


def test_empty_raises():
    with pytest.raises(Exception) as exc:
        _execute("   ")
    assert "asset id" in str(exc.value).lower()


def test_node_id():
    schema = nodes_asset.ArkSDAssetManual.define_schema()
    assert schema.node_id == "ArkSD_AssetManual"
    assert [i.id for i in schema.inputs] == ["asset_id"]
