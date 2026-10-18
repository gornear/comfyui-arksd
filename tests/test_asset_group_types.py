"""Regression tests for the reported asset and draft issues."""

import asyncio
from unittest.mock import patch

from nodes import asset_client


def _creds():
    return {"accessKey": "k", "secretKey": "s", "region": "cn-beijing"}


def test_group_type_all_queries_every_group_type():
    """Selecting 'All' must merge AIGC and LivenessFace, not silently pick AIGC.

    Authorized real-person assets live under LivenessFace, so a single-type
    query hides them.
    """
    seen = []

    async def fake_call(creds, action, body):
        seen.append(body["Filter"]["GroupType"])
        return {"Items": [{"Id": f"{body['Filter']['GroupType']}-1"}]}

    with patch.object(asset_client, "_call", fake_call):
        items = asyncio.run(asset_client.list_assets(_creds(), group_type="All"))

    assert sorted(seen) == ["AIGC", "LivenessFace"]
    assert sorted(item["Id"] for item in items) == ["AIGC-1", "LivenessFace-1"]


def test_group_type_single_still_queries_once():
    seen = []

    async def fake_call(creds, action, body):
        seen.append(body["Filter"]["GroupType"])
        return {"Items": []}

    with patch.object(asset_client, "_call", fake_call):
        asyncio.run(asset_client.list_assets(_creds(), group_type="LivenessFace"))

    assert seen == ["LivenessFace"]


def test_asset_groups_all_queries_every_group_type():
    seen = []

    async def fake_call(creds, action, body):
        seen.append(body["Filter"]["GroupType"])
        return {"Items": [{"Id": f"{body['Filter']['GroupType']}-g"}]}

    with patch.object(asset_client, "_call", fake_call):
        groups = asyncio.run(asset_client.list_asset_groups(_creds(), group_type="All"))

    assert sorted(seen) == ["AIGC", "LivenessFace"]
    assert len(groups) == 2
