"""The ArkSD Draft to Video node.

Seedance 2.5 draft mode is a two-step flow:

1. Generate a 480p draft with ``draft=true`` on the 2.5 node. That node outputs
   the draft task id.
2. Feed that id here to produce the 1080p final.

Ark reuses the draft's prompt, references, duration, ratio, seed,
``generate_audio``, and task type automatically. Sending any of those again is
an error even when the value matches, so this node deliberately does not expose
them. Only the parameters Ark allows to be re-specified are inputs here.
"""

import io as _io
import logging

from comfy_api.latest import io
from comfy_api.latest._input_impl.video_types import VideoFromFile
from comfy_execution.graph_utils import ExecutionBlocker

from . import client, config
from .constants import (
    DEFAULT_POLL_INTERVAL,
    DEFAULT_TIMEOUT,
    DRAFT_FINAL_RESOLUTION,
    EXPIRES_DEFAULT,
    EXPIRES_MAX,
    EXPIRES_MIN,
    MAX_TIMEOUT,
    MIN_TIMEOUT,
    MODELS,
    PRIORITY_MAX,
    PRIORITY_MIN,
)

LOGGER = logging.getLogger("arksd")

OUTPUT_FORMATS = ["mp4", "mov"]

# Parameters Ark re-specifies on the final pass. Everything else is forbidden.
RESPECIFIABLE = (
    "output_format",
    "watermark",
    "return_last_frame",
    "priority",
    "execution_expires_after",
)


def build_draft_body(draft_task_id: str, params: dict) -> dict:
    """Assemble the final-video request for a draft task id."""
    body: dict = {
        "model": MODELS["seedance_2_5"].model_id,
        "content": [{"type": "draft_task", "draft_task": {"id": draft_task_id}}],
        # Ark requires resolution here and only accepts 1080p.
        "resolution": DRAFT_FINAL_RESOLUTION,
    }
    for key in RESPECIFIABLE:
        value = params.get(key)
        if value is not None:
            body[key] = value
    return body


class ArkSDDraftToVideo(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="ArkSD_DraftToVideo",
            display_name="ArkSD Draft to Video",
            category="api node/ArkSD",
            description=(
                "Turn a Seedance 2.5 draft task id into the 1080p final video. "
                "Prompt, references, duration, ratio and seed are reused from the "
                "draft automatically."
            ),
            inputs=[
                io.Combo.Input(
                    "api_key_name",
                    options=config.list_api_key_names() or ["<none>"],
                    tooltip="Which entry of api_keys.json to use.",
                ),
                io.String.Input(
                    "draft_task_id",
                    default="",
                    tooltip="Task id returned by the Seedance 2.5 node with draft enabled.",
                ),
                io.Combo.Input("output_format", options=OUTPUT_FORMATS, default="mp4", optional=True),
                io.Boolean.Input("watermark", default=False, optional=True),
                io.Boolean.Input("return_last_frame", default=False, optional=True),
                io.Int.Input(
                    "priority",
                    default=0,
                    min=PRIORITY_MIN,
                    max=PRIORITY_MAX,
                    optional=True,
                    tooltip="Queue priority, 0-9.",
                ),
                io.Int.Input(
                    "execution_expires_after",
                    default=EXPIRES_DEFAULT,
                    min=EXPIRES_MIN,
                    max=EXPIRES_MAX,
                    optional=True,
                    tooltip="Task expiry in seconds from creation.",
                ),
                io.Int.Input(
                    "timeout",
                    default=DEFAULT_TIMEOUT,
                    min=MIN_TIMEOUT,
                    max=MAX_TIMEOUT,
                    tooltip="How long to wait for the video before giving up.",
                ),
                io.Float.Input(
                    "poll_interval",
                    default=DEFAULT_POLL_INTERVAL,
                    min=1.0,
                    max=60.0,
                    step=1.0,
                ),
                io.Boolean.Input(
                    "non_blocking",
                    default=False,
                    tooltip="Return the task id immediately instead of waiting.",
                ),
            ],
            outputs=[
                io.Video.Output("video"),
                io.String.Output("task_id", tooltip="Task id of the final video."),
            ],
        )

    @classmethod
    async def execute(cls, **kwargs) -> io.NodeOutput:
        draft_task_id = (kwargs.get("draft_task_id") or "").strip()
        if not draft_task_id:
            raise config.ConfigError(
                "No draft task id. Enable draft on ArkSD Seedance 2.5, run it, and "
                "connect its task_id output here."
            )
        api_key = config.get_api_key(kwargs["api_key_name"])
        body = build_draft_body(draft_task_id, kwargs)

        LOGGER.info("[ArkSD] rendering draft %s to %s", draft_task_id, DRAFT_FINAL_RESOLUTION)
        task_id = await client.create_task(api_key, body)
        if kwargs.get("non_blocking"):
            return io.NodeOutput(
                ExecutionBlocker(
                    "Non-blocking mode returns no video. Use ArkSD Query Task "
                    "with this task id to fetch it."
                ),
                task_id,
            )

        task = await client.wait_for_task(
            api_key,
            task_id,
            timeout=float(kwargs.get("timeout") or DEFAULT_TIMEOUT),
            poll_interval=float(kwargs.get("poll_interval") or DEFAULT_POLL_INTERVAL),
        )
        video_url = (task.get("content") or {}).get("video_url")
        if not video_url:
            raise client.ArkError("MissingVideo", f"Task {task_id} succeeded without a video_url")
        data = await client.download_video(video_url)
        LOGGER.info("[ArkSD] final video ready for draft %s", draft_task_id)
        return io.NodeOutput(VideoFromFile(_io.BytesIO(data)), task_id)
