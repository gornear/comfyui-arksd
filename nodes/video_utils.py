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
