import pytest
from nodes import nodes_task


def test_terminal_status_raises():
    with pytest.raises(nodes_task.TaskTerminalError):
        nodes_task.raise_if_terminal({"status": "failed", "error": {"code": "X", "message": "boom"}})


def test_succeeded_is_terminal_but_ok():
    nodes_task.raise_if_terminal({"status": "succeeded", "content": {"video_url": "u"}})


def test_running_is_not_terminal():
    nodes_task.raise_if_terminal({"status": "running"})


# ------------------------------------------------- ArkSD Query Task outputs


def _query_task(**overrides):
    from unittest.mock import patch
    import asyncio
    from nodes import client, config, nodes_task

    kwargs = {
        "api_key_name": "A",
        "task_id": "cgt-123",
        "timeout": 60,
        "poll_interval": 1.0,
    }
    kwargs.update(overrides)
    task = {
        "status": "succeeded",
        "content": {"video_url": "https://example/v.mp4"},
        "seed": 77,
    }
    with patch.object(config, "get_api_key", return_value="k"), patch.object(
        client, "get_task", return_value=task
    ), patch.object(client, "download_video", return_value=b"data"):
        return asyncio.run(nodes_task.ArkSDQueryTask.execute(**kwargs))


def test_query_task_exposes_task_id_output():
    schema = nodes_task_schema()
    assert "task_id" in schema


def nodes_task_schema():
    from nodes import nodes_task

    return [o.id for o in nodes_task.ArkSDQueryTask.define_schema().outputs]


def test_query_task_returns_the_id_it_was_given():
    result = _query_task(task_id="cgt-abc")
    assert result.args[3] == "cgt-abc"


def test_query_task_still_returns_video_seed_status():
    result = _query_task()
    assert result.args[0] is not None  # video
    assert result.args[1] == 77  # seed
    assert result.args[2] == "succeeded"  # status
