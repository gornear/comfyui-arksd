"""Task lookup nodes.

``ArkSD Query Task`` is an execution node: it blocks on a known task id and
emits the finished video. ``ArkSD Task List`` is a pure UI node with no sockets
and no execution work; its frontend extension browses, auto-refreshes, and
cancels queued tasks over HTTP so it keeps working while the queue is busy.
"""

import io as _io
import logging

from comfy_api.latest import io
from comfy_api.latest._input_impl.video_types import VideoFromFile

from . import client, config
from .constants import DEFAULT_POLL_INTERVAL, DEFAULT_TIMEOUT, MAX_TIMEOUT, MIN_TIMEOUT

LOGGER = logging.getLogger("arksd")

# States that will never change again. Only 'succeeded' still carries a video.
TERMINAL_STATUSES = {"succeeded", "failed", "cancelled", "expired"}


class TaskTerminalError(Exception):
    """Raised when a task has already ended without a usable video."""


def raise_if_terminal(task: dict) -> None:
    """Raise when ``task`` has finished in a state that has no video.

    A ``succeeded`` task returns normally so the caller can download it. A
    non-terminal task also returns normally so the caller can poll it.
    """
    status = task.get("status")
    if status == "succeeded" or status not in TERMINAL_STATUSES:
        return
    error = task.get("error") or {}
    detail = error.get("message") or f"status is {status}"
    code = error.get("code") or status
    raise TaskTerminalError(f"Task ended with {code}: {detail}")


class ArkSDQueryTask(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="ArkSD_QueryTask",
            display_name="ArkSD Query Task",
            category="api node/ArkSD",
            description=(
                "Fetch one Seedance task by id and wait for its video. Useful after "
                "a non-blocking submission."
            ),
            inputs=[
                io.Combo.Input(
                    "api_key_name",
                    options=config.list_api_key_names() or ["<none>"],
                    tooltip="Which entry of api_keys.json to use.",
                ),
                io.String.Input(
                    "task_id",
                    default="",
                    tooltip="Task id to query, for example from a non-blocking run.",
                ),
                io.Int.Input(
                    "timeout",
                    default=DEFAULT_TIMEOUT,
                    min=MIN_TIMEOUT,
                    max=MAX_TIMEOUT,
                    tooltip="How long to wait if the task is still running.",
                ),
                io.Float.Input(
                    "poll_interval",
                    default=DEFAULT_POLL_INTERVAL,
                    min=1.0,
                    max=60.0,
                    step=1.0,
                ),
            ],
            outputs=[
                io.Video.Output("video"),
                io.Int.Output("seed"),
                io.String.Output("status"),
            ],
        )

    @classmethod
    async def execute(cls, **kwargs) -> io.NodeOutput:
        task_id = (kwargs.get("task_id") or "").strip()
        if not task_id:
            raise config.ConfigError("No task id given to ArkSD Query Task.")
        api_key = config.get_api_key(kwargs["api_key_name"])

        # Check the current state first so an already-finished task fails fast
        # instead of polling until the timeout.
        task = await client.get_task(api_key, task_id)
        raise_if_terminal(task)

        if task.get("status") != "succeeded":
            task = await client.wait_for_task(
                api_key,
                task_id,
                timeout=float(kwargs.get("timeout") or DEFAULT_TIMEOUT),
                poll_interval=float(kwargs.get("poll_interval") or DEFAULT_POLL_INTERVAL),
            )

        video_url = (task.get("content") or {}).get("video_url")
        if not video_url:
            raise client.ArkError("MissingVideo", f"Task {task_id} has no video_url")
        data = await client.download_video(video_url)
        LOGGER.info("[ArkSD] queried task %s (seed=%s)", task_id, task.get("seed"))
        return io.NodeOutput(
            VideoFromFile(_io.BytesIO(data)), task.get("seed"), task.get("status")
        )


class ArkSDTaskList(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="ArkSD_TaskList",
            display_name="ArkSD Task List",
            category="api node/ArkSD",
            description=(
                "Browse recent Seedance tasks, auto-refresh every 10 seconds, and "
                "cancel queued tasks. Runs independently of the ComfyUI queue."
            ),
            inputs=[
                io.Combo.Input(
                    "api_key_name",
                    options=config.list_api_key_names() or ["<none>"],
                    tooltip="Which entry of api_keys.json to use for listing and cancelling tasks.",
                ),
            ],
            outputs=[],
            is_output_node=False,
        )

    @classmethod
    def execute(cls, api_key_name="") -> io.NodeOutput:
        # Everything happens in the frontend extension; there is nothing to run.
        return io.NodeOutput()
