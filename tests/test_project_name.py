"""ProjectName must be forwarded to the asset APIs.

Assets live inside an Ark project. The API defaults to ``default`` but returns
an empty list for any other project, so a user whose authorized assets live in
a named project sees nothing unless the project is passed through.
"""

import asyncio
from unittest.mock import patch

from nodes import asset_client


def _creds():
    return {"accessKey": "k", "secretKey": "s", "region": "cn-beijing"}


def test_list_assets_forwards_project_name():
    seen = []

    async def fake_call(creds, action, body):
        seen.append(body.get("ProjectName"))
        return {"Items": []}

    with patch.object(asset_client, "_call", fake_call):
        asyncio.run(
            asset_client.list_assets(_creds(), group_type="AIGC", project_name="cv1-abcde")
        )

    assert seen == ["cv1-abcde"]


def test_list_assets_defaults_project_to_default():
    seen = []

    async def fake_call(creds, action, body):
        seen.append(body.get("ProjectName"))
        return {"Items": []}

    with patch.object(asset_client, "_call", fake_call):
        asyncio.run(asset_client.list_assets(_creds(), group_type="AIGC"))

    assert seen == ["default"]


def test_list_asset_groups_forwards_project_name():
    seen = []

    async def fake_call(creds, action, body):
        seen.append(body.get("ProjectName"))
        return {"Items": []}

    with patch.object(asset_client, "_call", fake_call):
        asyncio.run(asset_client.list_asset_groups(_creds(), group_type="All", project_name="p1"))

    assert seen == ["p1", "p1"]
