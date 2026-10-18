"""Regression tests for the final review findings."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from nodes import asset_client, nodes_video, routes
from nodes.constants import MODELS


def test_list_assets_does_not_send_unsupported_filter_fields():
    """The ListAssets Filter only accepts GroupType, GroupIds, Name, Statuses.

    Asset type filtering has to happen client-side; sending an unknown
    AssetTypes field would make the API reject the request.
    """
    captured = {}

    async def fake_call(creds, action, body):
        captured["action"] = action
        captured["body"] = body
        return {"Items": [
            {"Id": "a1", "AssetType": "Image"},
            {"Id": "a2", "AssetType": "Video"},
        ]}

    with patch.object(asset_client, "_call", fake_call):
        items = asyncio.run(
            asset_client.list_assets(
                {"accessKey": "k", "secretKey": "s", "region": "cn-beijing"},
                group_type="AIGC",
                asset_type="Video",
            )
        )

    assert set(captured["body"]["Filter"]) <= {"GroupType", "GroupIds", "Name", "Statuses"}
    assert [item["Id"] for item in items] == ["a2"]


def test_build_body_omits_last_frame_when_false_for_20():
    """return_last_frame=False must not leak into a body the model rejects."""
    body = nodes_video.build_body(MODELS["seedance_2_0"], {
        "prompt": "x", "resolution": "720p", "ratio": "adaptive",
        "duration": 5, "seed": -1, "watermark": False, "generate_audio": True,
        "images": [], "videos": [], "audios": [],
        "return_last_frame": False,
    })
    assert "return_last_frame" not in body


def test_page_params_fall_back_on_bad_input():
    """A malformed page_num must not become a 500."""
    assert routes._int_param({"page_num": "abc"}, "page_num", 1) == 1
    assert routes._int_param({"page_num": "7"}, "page_num", 1) == 7
