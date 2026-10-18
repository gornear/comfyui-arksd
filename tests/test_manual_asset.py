"""ArkSD Asset owns only the picker; manual entry lives in its own node."""

import pytest

from nodes import nodes_asset


def test_picker_value_is_used():
    result = nodes_asset.ArkSDAsset.execute(
        ak_sk_name="A",
        group_type="AIGC",
        group_id="",
        asset_type="Image",
        asset_id="asset-from-picker",
        refresh=False,
        project_name="default",
    )
    assert result.args[0] == "asset://asset-from-picker"


def test_empty_selection_raises():
    with pytest.raises(Exception) as exc:
        nodes_asset.ArkSDAsset.execute(
            ak_sk_name="A",
            group_type="AIGC",
            group_id="",
            asset_type="Image",
            asset_id="",
            refresh=False,
            project_name="default",
        )
    assert "asset" in str(exc.value).lower()


def test_schema_has_no_manual_input():
    schema = nodes_asset.ArkSDAsset.define_schema()
    ids = [i.id for i in schema.inputs]
    assert "manual_asset_id" not in ids
    assert ids == [
        "ak_sk_name",
        "group_type",
        "project_name",
        "group_id",
        "asset_type",
        "asset_id",
        "refresh",
    ]
