import pytest
from nodes import nodes_task


def test_terminal_status_raises():
    with pytest.raises(nodes_task.TaskTerminalError):
        nodes_task.raise_if_terminal({"status": "failed", "error": {"code": "X", "message": "boom"}})


def test_succeeded_is_terminal_but_ok():
    nodes_task.raise_if_terminal({"status": "succeeded", "content": {"video_url": "u"}})


def test_running_is_not_terminal():
    nodes_task.raise_if_terminal({"status": "running"})
