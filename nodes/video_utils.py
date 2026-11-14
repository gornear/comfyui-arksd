"""Read the last frame of a video without decoding all of it.

``GetVideoComponents`` decodes every frame into a tensor, which costs gigabytes
for a long clip when all that is wanted is the final frame. This seeks close to
the end and decodes only the remaining frames.

The usual reason to want it: chain one clip's last frame into the next clip's
first frame.
"""

import io
import logging

import av
import numpy as np
import torch

LOGGER = logging.getLogger("arksd")

# Seek back this many seconds before the end. Enough to cover a GOP without
# decoding much.
SEEK_BACK_SECONDS = 3

# Hardware encoders come first so a machine with NVENC uses it without asking.
# The list is also the fallback order when one of them cannot be opened.
H264_ENCODERS = ["h264_nvenc", "libx264"]
AV1_ENCODERS = ["av1_nvenc", "libsvtav1"]

# The node exposes these five names for both encoders. x264 has nine steps but
# several of them sit within a few percent of each other; the NVENC side really
# only has five, because p4/p5 and p6/p7 are near twins and p1/p2 are the low
# latency modes, which produce bigger files than p3.
PRESETS = ["fastest", "fast", "medium", "slow", "slowest"]

X264_PRESET = {
    "fastest": "ultrafast",
    "fast": "veryfast",
    "medium": "medium",
    "slow": "slow",
    "slowest": "veryslow",
}

NVENC_PRESET = {
    "fastest": "p1",
    "fast": "p3",
    "medium": "p4",
    "slow": "p6",
    "slowest": "p7",
}

# SVT-AV1 numbers run 0-13 with larger being faster, the opposite direction of
# the x264 names.
SVT_AV1_PRESET = {
    "fastest": "12",
    "fast": "10",
    "medium": "8",
    "slow": "6",
    "slowest": "4",
}


def pick_video_encoder(candidates: list[str]) -> str | None:
    """Return the first of ``candidates`` this build can encode with."""
    for name in candidates:
        try:
            av.codec.Codec(name, "w")
        except (av.FFmpegError, ValueError):
            continue
        return name
    return None


def video_encoder_options(encoder: str, crf: int, preset: str) -> dict[str, str]:
    """Return the PyAV stream options for ``encoder`` at ``crf`` and ``preset``."""
    if encoder.endswith("_nvenc"):
        # constqp+qp looks like it sets quality on av1_nvenc but is ignored; the
        # VBR constant-quality pair is the one that actually varies the bitrate.
        return {"rc": "vbr", "cq": str(crf), "b:v": "0", "preset": NVENC_PRESET[preset]}
    if encoder == "libsvtav1":
        return {"crf": str(crf), "preset": SVT_AV1_PRESET[preset]}
    return {"crf": str(crf), "preset": X264_PRESET[preset]}


def extract_last_frame(data: bytes) -> torch.Tensor:
    """Return the last frame as ``[1, H, W, 3]`` float32 in 0-1."""
    try:
        return _extract(data)
    except av.FFmpegError as exc:
        # PyAV's raw error is a list of errno values; say something readable.
        raise ValueError(f"ArkSD: could not decode the video: {exc}") from exc


def _extract(data: bytes) -> torch.Tensor:
    with av.open(io.BytesIO(data)) as container:
        if not container.streams.video:
            raise ValueError("ArkSD: could not decode the video, it has no video stream.")
        stream = container.streams.video[0]

        # Seek by duration rather than stream.frames: containers do not always
        # write a frame count.
        if stream.duration and stream.time_base:
            back = int(SEEK_BACK_SECONDS / stream.time_base)
            container.seek(max(0, stream.duration - back), stream=stream, backward=True)

        last = None
        for frame in container.decode(stream):
            last = frame

    if last is None:
        raise ValueError("ArkSD: could not decode any frame from the video.")
    array = last.to_ndarray(format="rgb24")
    frame = torch.from_numpy(np.ascontiguousarray(array)).float().div_(255.0)
    LOGGER.info("[ArkSD] last frame extracted (%dx%d)", last.width, last.height)
    return frame.unsqueeze(0)
