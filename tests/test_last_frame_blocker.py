"""last_frame must block downstream nodes instead of handing them None.

Handing None to a consumer such as SaveImage crashes with
"'NoneType' object is not subscriptable". ComfyUI's ExecutionBlocker is the
supported way to say "this output produced nothing".
"""

import asyncio
from unittest.mock import patch

from comfy_execution.graph_utils import ExecutionBlocker

from nodes import client, config, nodes_video
from nodes.constants import MODELS


def _task_without_last_frame():
    return {
        "status": "succeeded",
        "content": {"video_url": "https://example/v.mp4"},
        "seed": 42,
    }


def _run(return_last_frame):
    params = {
        "api_key_name": "A",
        "prompt": "x",
        "resolution": "480p",
        "ratio": "adaptive",
        "duration": 5,
        "seed": -1,
        "watermark": False,
        "generate_audio": True,
        "images": [],
        "videos": [],
        "audios": [],
        "timeout": 60,
        "poll_interval": 1.0,
        "non_blocking": False,
        "return_last_frame": return_last_frame,
    }
    with patch.object(config, "get_api_key", return_value="k"), patch.object(
        client, "create_task", return_value="cgt-1"
    ), patch.object(client, "wait_for_task", return_value=_task_without_last_frame()), patch.object(
        client, "download_video", return_value=b"data"
    ):
        return asyncio.run(nodes_video._run(MODELS["seedance_2_0_mini"], params))


def test_missing_last_frame_blocks_downstream():
    result = _run(return_last_frame=False)
    last = result.args[3]
    assert isinstance(last, ExecutionBlocker)
    assert last.message


def test_video_and_seed_still_produced():
    result = _run(return_last_frame=False)
    assert result.args[0] is not None  # video
    assert result.args[1] == 42  # seed
    assert result.args[2] == "cgt-1"  # task id


def test_non_blocking_also_blocks_last_frame():
    params = {
        "api_key_name": "A",
        "prompt": "x",
        "resolution": "480p",
        "ratio": "adaptive",
        "duration": 5,
        "seed": -1,
        "watermark": False,
        "generate_audio": True,
        "images": [],
        "videos": [],
        "audios": [],
        "non_blocking": True,
        "return_last_frame": False,
    }
    with patch.object(config, "get_api_key", return_value="k"), patch.object(
        client, "create_task", return_value="cgt-1"
    ):
        result = asyncio.run(nodes_video._run(MODELS["seedance_2_0_mini"], params))
    assert isinstance(result.args[3], ExecutionBlocker)


def test_draft_non_blocking_blocks_video():
    from nodes import nodes_draft

    params = {
        "api_key_name": "A",
        "draft_task_id": "cgt-draft",
        "non_blocking": True,
        "output_format": "mp4",
        "watermark": False,
        "return_last_frame": False,
        "priority": 0,
        "execution_expires_after": 172800,
        "timeout": 60,
        "poll_interval": 1.0,
    }
    with patch.object(config, "get_api_key", return_value="k"), patch.object(
        client, "create_task", return_value="cgt-final"
    ):
        result = asyncio.run(nodes_draft.ArkSDDraftToVideo.execute(**params))
    assert isinstance(result.args[0], ExecutionBlocker)
    assert result.args[1] == "cgt-final"
