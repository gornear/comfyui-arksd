"""The four Seedance generation nodes.

Each model gets its own node because their parameter sets differ and because
``io.Autogrow`` maxima are fixed at node-definition time: a single node with a
model combo could not declare the right number of reference slots.

Common behaviour:

* ``reference_image_N`` accepts an ``IMAGE`` tensor (converted to base64) or a
  ``STRING`` (``asset://<id>`` or a public URL).
* ``reference_video_N`` accepts a ``VIDEO`` (inlined as base64 within the size
  and duration gates in ``_normalize_video``) or a ``STRING``.
* ``reference_audio_N`` accepts an ``AUDIO`` (encoded to WAV within the gates in
  ``_normalize_audio``) or a ``STRING``.
* Outputs are the video, the seed actually used, the task id, and the last
  frame.
"""

import base64
import io as _io
import logging
import wave

import torch

from comfy_api.latest import io

from comfy_api.latest._input_impl.video_types import VideoFromFile
from comfy_execution.graph_utils import ExecutionBlocker

from . import client, config, image_utils
from .constants import (
    AUDIO_MAX_BYTES,
    AUDIO_MIME,
    AUDIO_SAMPLE_WIDTH,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_TIMEOUT,
    DRAFT_RESOLUTION,
    VIDEO_MAX_BYTES,
    VIDEO_MIME,
    MAX_TIMEOUT,
    MIN_TIMEOUT,
    MODELS,
    PRIORITY_MAX,
    PRIORITY_MIN,
    RATIOS,
    SEED_MAX,
    SEED_MIN,
)

LOGGER = logging.getLogger("arksd")

TASK_TYPES = ["auto", "reference", "edit", "extend"]
OUTPUT_FORMATS = ["mp4", "mov"]


def _sorted_slots(slots: dict | None) -> list[str]:
    """Return connected slot values, ordered by the numeric key suffix."""
    if not slots:
        return []
    ordered = sorted(
        slots.items(),
        key=lambda item: int(item[0].rsplit("_", 1)[-1]) if item[0].rsplit("_", 1)[-1].isdigit() else 0,
    )
    return [value for _, value in ordered if value is not None]


def collect_references(images, videos, audios) -> tuple[list, list, list]:
    """Flatten the three autogrow dicts into ordered lists."""
    return _sorted_slots(images), _sorted_slots(videos), _sorted_slots(audios)


def _normalize_images(images: list) -> list:
    """Convert IMAGE tensors to data URLs and pass STRING references through."""
    result = []
    for index, value in enumerate(images):
        if isinstance(value, str):
            result.append(value)
        else:
            result.append(image_utils.normalize_image(value, f"reference_image_{index}"))
    return result


def _video_duration_seconds(video) -> float | None:
    """Return the video length in seconds, or None when it cannot be read."""
    try:
        components = video.get_components()
        frame_rate = float(components.frame_rate)
        frames = int(components.images.shape[0])
    except (AttributeError, TypeError, ValueError):
        return None
    if frame_rate <= 0:
        return None
    return frames / frame_rate


def _normalize_video(value, index: int, spec) -> str:
    """Return a reference video as a URL, an asset id, or a base64 data URI.

    A ``STRING`` is an ``asset://`` id or a public URL and is returned as-is.
    A local ``VIDEO`` is inlined as base64, but only when it fits both gates:

    * at most :data:`VIDEO_MAX_BYTES`, because the whole request body is capped
      at 64 MB and Ark advises against base64 for large files;
    * no longer than the model's own maximum output duration, since a reference
      video longer than that can never be used.

    Refusing here, with the real limit in the message, is better than letting
    Ark reject an oversized body.
    """
    if isinstance(value, str):
        return value

    duration = _video_duration_seconds(value)
    if duration is not None and duration > spec.duration_max:
        raise ValueError(
            f"ArkSD: reference_video_{index} is {duration:.1f}s long, but "
            f"{spec.model_id} accepts reference videos up to {spec.duration_max}s. "
            f"Trim the video or use a different model."
        )

    source = value.get_stream_source()
    if hasattr(source, "read"):
        payload = source.read()
    else:
        with open(source, "rb") as handle:
            payload = handle.read()

    if len(payload) > VIDEO_MAX_BYTES:
        raise ValueError(
            f"ArkSD: reference_video_{index} is {len(payload) / (1024 * 1024):.1f} MB, "
            f"but an inlined reference video is limited to "
            f"{VIDEO_MAX_BYTES // (1024 * 1024)} MB. Upload it to your Ark asset "
            f"library and use an asset:// id, or host it at a public URL."
        )

    encoded = base64.b64encode(payload).decode("ascii")
    LOGGER.info(
        "[ArkSD] reference_video_%d inlined (%d KB base64)", index, len(encoded) // 1024
    )
    return f"data:{VIDEO_MIME};base64,{encoded}"


def _normalize_audio(value, index: int, spec) -> str:
    """Return a reference audio as a URL, an asset id, or a base64 data URI.

    ComfyUI's AUDIO value is an in-memory waveform whose source format has
    already been decoded by whichever loader produced it, so there is no format
    mismatch to resolve: the waveform is encoded to 16-bit PCM WAV and inlined.

    The duration gate matches the video one (2.5 allows 30 s, the 2.0 family
    15 s). The size gate exists because WAV is uncompressed, which inflates an
    already-decoded waveform well past Ark's 15 MB limit on the original file.
    """
    if isinstance(value, str):
        return value

    waveform = value["waveform"]
    # comfy_api declares the key as `sampler_rate`, but LoadAudio and the other
    # audio helpers emit `sample_rate`. Accept either.
    sample_rate = int(value.get("sample_rate") or value.get("sampler_rate") or 0)

    if waveform.dim() == 3:
        channels = int(waveform.shape[1])
        samples = waveform
    elif waveform.dim() == 2:
        channels = int(waveform.shape[0])
        samples = waveform.unsqueeze(0)
    else:
        raise ValueError(
            f"ArkSD: reference_audio_{index} has an unexpected waveform shape "
            f"{tuple(waveform.shape)}."
        )

    frames = int(samples.shape[-1])
    duration = frames / sample_rate if sample_rate > 0 else 0.0
    if duration > spec.duration_max:
        raise ValueError(
            f"ArkSD: reference_audio_{index} is {duration:.1f}s long, but "
            f"{spec.model_id} accepts reference audio up to {spec.duration_max}s. "
            f"Trim it or use a different model."
        )

    # [1, channels, frames] float 0-1 -> interleaved int16 PCM.
    pcm = (
        samples[0]
        .transpose(0, 1)
        .clamp(0.0, 1.0)
        .mul(32767.0)
        .round()
        .to("cpu")
        .to(torch.int16)
        .numpy()
        .tobytes()
    )

    buffer = _io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(AUDIO_SAMPLE_WIDTH)
        handle.setframerate(sample_rate)
        handle.writeframes(pcm)
    payload = buffer.getvalue()

    if len(payload) > AUDIO_MAX_BYTES:
        raise ValueError(
            f"ArkSD: reference_audio_{index} encodes to "
            f"{len(payload) / (1024 * 1024):.1f} MB of WAV, over the "
            f"{AUDIO_MAX_BYTES // (1024 * 1024)} MB limit. Use a shorter clip, a "
            f"lower sample rate, or upload it to your Ark asset library and pass "
            f"an asset:// id."
        )

    encoded = base64.b64encode(payload).decode("ascii")
    LOGGER.info(
        "[ArkSD] reference_audio_%d inlined (%d KB base64, %.1fs)",
        index,
        len(encoded) // 1024,
        duration,
    )
    return f"data:{AUDIO_MIME};base64,{encoded}"


def _decode_last_frame(data: bytes):
    """Decode a last-frame JPEG into a ComfyUI IMAGE tensor of shape [1, H, W, 3]."""
    import numpy as np
    import torch
    from PIL import Image

    image = Image.open(_io.BytesIO(data)).convert("RGB")
    array = np.asarray(image).astype("float32") / 255.0
    return torch.from_numpy(array)[None, ...]


def _blocked_last_frame(reason: str) -> ExecutionBlocker:
    """Return a blocker for the last_frame output.

    Handing None to a consumer such as SaveImage crashes with
    "'NoneType' object is not subscriptable", so the output is blocked instead:
    downstream nodes are skipped with this message.
    """
    return ExecutionBlocker(reason)


async def _last_frame_output(task: dict):
    """Return the last-frame tensor, or an ExecutionBlocker when absent."""
    url = (task.get("content") or {}).get("last_frame_url")
    if not url:
        return _blocked_last_frame(
            "This task produced no last frame. Enable return_last_frame on the "
            "ArkSD node to get one, or disconnect the last_frame output."
        )
    data = await client.download_video(url)
    return _decode_last_frame(data)


def build_body(spec, params: dict) -> dict:
    """Assemble a create-task request body for ``spec``.

    Parameters a model does not support are dropped rather than sent, because
    Ark validates strictly and rejects unknown or inapplicable fields.
    """
    content = client.build_content(
        params.get("prompt") or "",
        params["images"],
        params["videos"],
        params["audios"],
    )
    body: dict = {
        "model": spec.model_id,
        "content": content,
        "resolution": params["resolution"],
        "ratio": params["ratio"],
        "duration": int(params["duration"]),
        "seed": int(params["seed"]),
        "watermark": bool(params["watermark"]),
        "generate_audio": bool(params["generate_audio"]),
    }
    # return_last_frame is only meaningful when true; Ark rejects an explicit
    # false on some models, so it is omitted rather than sent as False.
    if params.get("return_last_frame"):
        body["return_last_frame"] = True

    if spec.supports_output_format and params.get("output_format"):
        body["output_format"] = params["output_format"]
    if spec.supports_task_type and params.get("omni_reference_task_type"):
        body["omni_reference_task_type"] = params["omni_reference_task_type"]
    if params.get("priority") is not None:
        body["priority"] = int(params["priority"])
    if params.get("execution_expires_after") is not None:
        body["execution_expires_after"] = int(params["execution_expires_after"])

    if spec.supports_draft and params.get("draft"):
        # Ark rejects any other resolution while draft mode is on.
        body["draft"] = True
        body["resolution"] = DRAFT_RESOLUTION
    return body


async def _run(spec, params: dict) -> io.NodeOutput:
    """Submit a task and either wait for it or return the task id."""
    api_key = config.get_api_key(params["api_key_name"])
    images = _normalize_images(params["images"])
    videos = [_normalize_video(v, i, spec) for i, v in enumerate(params["videos"])]
    audios = [_normalize_audio(a, i, spec) for i, a in enumerate(params["audios"])]
    body = build_body(spec, {**params, "images": images, "videos": videos, "audios": audios})

    LOGGER.info(
        "[ArkSD] submitting %s (resolution=%s, duration=%s, refs=%d/%d/%d)",
        body["model"],
        body["resolution"],
        body["duration"],
        len(images),
        len(videos),
        len(audios),
    )
    task_id = await client.create_task(api_key, body)

    if params.get("non_blocking"):
        LOGGER.info("[ArkSD] submitted task %s (non-blocking)", task_id)
        # seed is -1 because the model has not picked one yet; use ArkSD Query
        # Task later to fetch the real seed with the video.
        return io.NodeOutput(
            None,
            -1,
            task_id,
            _blocked_last_frame("Non-blocking mode returns no video or last frame."),
        )

    task = await client.wait_for_task(
        api_key,
        task_id,
        timeout=float(params.get("timeout") or DEFAULT_TIMEOUT),
        poll_interval=float(params.get("poll_interval") or DEFAULT_POLL_INTERVAL),
    )
    video_url = (task.get("content") or {}).get("video_url")
    if not video_url:
        raise client.ArkError("MissingVideo", f"Task {task_id} succeeded without a video_url")
    data = await client.download_video(video_url)
    seed = task.get("seed")
    last_frame = await _last_frame_output(task)
    LOGGER.info(
        "[ArkSD] task %s finished (seed=%s, %d bytes, last_frame=%s)",
        task_id,
        seed,
        len(data),
        "no" if isinstance(last_frame, ExecutionBlocker) else "yes",
    )
    return io.NodeOutput(VideoFromFile(_io.BytesIO(data)), seed, task_id, last_frame)


def _common_inputs(spec) -> list:
    """Inputs shared by every generation node."""
    return [
        io.Combo.Input(
            "api_key_name",
            options=config.list_api_key_names() or ["<none>"],
            tooltip="Which entry of api_keys.json to use.",
        ),
        io.String.Input(
            "prompt",
            default="",
            multiline=True,
            tooltip="Text prompt. References are cited as @image1, @video1 in the prompt.",
        ),
        io.Combo.Input(
            "resolution",
            options=spec.resolutions,
            default=spec.default_resolution,
        ),
        io.Combo.Input("ratio", options=RATIOS, default="adaptive"),
        io.Int.Input(
            "duration",
            default=spec.duration_default,
            min=-1,
            max=spec.duration_max,
            tooltip=(
                f"Seconds. {spec.duration_min}-{spec.duration_max}, or -1 to let the "
                "model choose."
            ),
        ),
        io.Int.Input("seed", default=-1, min=SEED_MIN, max=SEED_MAX),
        io.Boolean.Input(
            "watermark",
            default=False,
            tooltip="Add the 'AI generated' watermark.",
        ),
        io.Boolean.Input(
            "generate_audio",
            default=True,
            tooltip="Generate synchronized audio with the video.",
        ),
        io.Boolean.Input(
            "return_last_frame",
            default=False,
            tooltip="Also return the last frame image.",
            optional=True,
        ),
        io.Int.Input(
            "priority",
            default=0,
            min=PRIORITY_MIN,
            max=PRIORITY_MAX,
            optional=True,
            tooltip="Queue priority, 0-9. Higher jumps ahead of lower priority tasks.",
        ),
        io.Int.Input(
            "execution_expires_after",
            default=172800,
            min=3600,
            max=259200,
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
            tooltip="Seconds between status checks.",
        ),
        io.Boolean.Input(
            "non_blocking",
            default=False,
            tooltip=(
                "Return the task id immediately instead of waiting. Use "
                "ArkSD Query Task later to fetch the video."
            ),
        ),
        io.Autogrow.Input(
            "reference_images",
            optional=True,
            template=io.Autogrow.TemplatePrefix(
                input=io.MultiType.Input("reference_image", [io.Image, io.String]),
                prefix="reference_image_",
                min=0,
                max=spec.max_images,
            ),
            tooltip="Reference images: a ComfyUI IMAGE or an asset:// / URL string.",
        ),
        io.Autogrow.Input(
            "reference_videos",
            optional=True,
            template=io.Autogrow.TemplatePrefix(
                # VIDEO comes from LoadVideo; STRING covers an asset:// id or a
                # public URL.
                input=io.MultiType.Input("reference_video", [io.Video, io.String]),
                prefix="reference_video_",
                min=0,
                max=spec.max_videos,
            ),
            tooltip=(
                "Reference videos: a ComfyUI VIDEO (inlined as base64, up to 30 MB "
                "and the model's max duration), or an asset:// / URL string."
            ),
        ),
        io.Autogrow.Input(
            "reference_audios",
            optional=True,
            template=io.Autogrow.TemplatePrefix(
                input=io.MultiType.Input("reference_audio", [io.Audio, io.String]),
                prefix="reference_audio_",
                min=0,
                max=spec.max_audios,
            ),
            tooltip=(
                "Reference audio: a ComfyUI AUDIO (inlined as WAV, up to 30 MB and "
                "the model's max duration), or an asset:// / URL string."
            ),
        ),
    ]


def _outputs() -> list:
    return [
        io.Video.Output("video"),
        io.Int.Output("seed", tooltip="The seed actually used by this task."),
        io.String.Output("task_id", tooltip="Ark task id, reusable with ArkSD Query Task."),
        io.Image.Output(
            "last_frame",
            tooltip="Last frame of the video. Only present when return_last_frame is on.",
        ),
    ]


def _collect_kwargs(kwargs: dict) -> dict:
    images, videos, audios = collect_references(
        kwargs.get("reference_images"), kwargs.get("reference_videos"), kwargs.get("reference_audios")
    )
    params = {**kwargs, "images": images, "videos": videos, "audios": audios}
    return params


class ArkSDSeedance25(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        spec = MODELS["seedance_2_5"]
        return io.Schema(
            node_id="ArkSD_Seedance25",
            display_name="ArkSD Seedance 2.5",
            category="api node/ArkSD",
            description=(
                "Doubao Seedance 2.5 video generation. Supports up to 30 images, "
                "10 videos and 10 audio references, draft mode, and video edit/extend."
            ),
            inputs=[
                *_common_inputs(spec),
                io.Combo.Input(
                    "output_format",
                    options=OUTPUT_FORMATS,
                    default="mp4",
                    tooltip="mp4 for compatibility, mov for high color fidelity post work.",
                ),
                io.Boolean.Input(
                    "draft",
                    default=True,
                    tooltip=(
                        "Draft mode: generate a 480p preview first. Feed the task id into "
                        "ArkSD Draft to Video to produce the 1080p final."
                    ),
                ),
                io.Combo.Input(
                    "omni_reference_task_type",
                    options=TASK_TYPES,
                    default="auto",
                    tooltip="Hint the task type to validate parameters earlier.",
                ),
            ],
            outputs=_outputs(),
        )

    @classmethod
    async def execute(cls, **kwargs) -> io.NodeOutput:
        return await _run(MODELS["seedance_2_5"], _collect_kwargs(kwargs))


class ArkSDSeedance20(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        spec = MODELS["seedance_2_0"]
        return io.Schema(
            node_id="ArkSD_Seedance20",
            display_name="ArkSD Seedance 2.0",
            category="api node/ArkSD",
            description=(
                "Doubao Seedance 2.0 video generation. Up to 9 images, 3 videos, "
                "3 audio references, and 4k output."
            ),
            inputs=_common_inputs(spec),
            outputs=_outputs(),
        )

    @classmethod
    async def execute(cls, **kwargs) -> io.NodeOutput:
        return await _run(MODELS["seedance_2_0"], _collect_kwargs(kwargs))


class ArkSDSeedance20Fast(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        spec = MODELS["seedance_2_0_fast"]
        return io.Schema(
            node_id="ArkSD_Seedance20Fast",
            display_name="ArkSD Seedance 2.0 Fast",
            category="api node/ArkSD",
            description="Doubao Seedance 2.0 Fast: lower cost and faster, 480p/720p only.",
            inputs=_common_inputs(spec),
            outputs=_outputs(),
        )

    @classmethod
    async def execute(cls, **kwargs) -> io.NodeOutput:
        return await _run(MODELS["seedance_2_0_fast"], _collect_kwargs(kwargs))


class ArkSDSeedance20Mini(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        spec = MODELS["seedance_2_0_mini"]
        return io.Schema(
            node_id="ArkSD_Seedance20Mini",
            display_name="ArkSD Seedance 2.0 Mini",
            category="api node/ArkSD",
            description="Doubao Seedance 2.0 Mini: lowest cost, 480p/720p only.",
            inputs=_common_inputs(spec),
            outputs=_outputs(),
        )

    @classmethod
    async def execute(cls, **kwargs) -> io.NodeOutput:
        return await _run(MODELS["seedance_2_0_mini"], _collect_kwargs(kwargs))
