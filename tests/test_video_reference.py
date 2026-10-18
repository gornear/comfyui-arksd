"""Local VIDEO references: size and duration gates, then base64.

Ark accepts a reference video only as a URL or an asset id. A local file from
LoadVideo can still be sent inline as base64, but the request body is capped at
64 MB, so anything large has to be refused up front with a clear message
instead of failing at the API.
"""

import base64
import io
from fractions import Fraction

import pytest
import torch

from nodes import nodes_video
from nodes.constants import MODELS


class FakeComponents:
    def __init__(self, frames: int, fps: int):
        self.frame_rate = Fraction(fps, 1)
        self.images = torch.zeros(frames, 8, 8, 3)


class FakeVideo:
    """Stand-in for ComfyUI's VideoInput with a controllable payload."""

    def __init__(self, payload: bytes, frames: int, fps: int):
        self._payload = payload
        self._frames = frames
        self._fps = fps

    def get_stream_source(self):
        return io.BytesIO(self._payload)

    def get_components(self):
        return FakeComponents(self._frames, self._fps)


def _video(payload: bytes, frames: int = 48, fps: int = 24):
    return FakeVideo(payload, frames, fps)


# ------------------------------------------------------------ size gate


def test_video_over_size_limit_is_refused():
    payload = b"x" * (nodes_video.VIDEO_MAX_BYTES + 1)
    with pytest.raises(ValueError) as exc:
        nodes_video._normalize_video(_video(payload), 0, MODELS["seedance_2_5"])
    assert "30" in str(exc.value)


def test_small_video_becomes_base64_data_uri():
    payload = b"small-video-bytes"
    uri = nodes_video._normalize_video(_video(payload), 0, MODELS["seedance_2_5"])
    assert uri.startswith("data:video/mp4;base64,")
    assert base64.b64decode(uri.split(",", 1)[1]) == payload


# -------------------------------------------------------- duration gate


def test_video_over_model_duration_is_refused():
    # 24 fps * 16 s = 384 frames, over the 15 s cap of Seedance 2.0.
    with pytest.raises(ValueError) as exc:
        nodes_video._normalize_video(_video(b"x", frames=384), 0, MODELS["seedance_2_0"])
    assert "15" in str(exc.value)


def test_video_within_duration_is_accepted():
    # 24 fps * 10 s = 240 frames, inside the 15 s cap of Seedance 2.0.
    uri = nodes_video._normalize_video(_video(b"x", frames=240), 0, MODELS["seedance_2_0"])
    assert uri.startswith("data:video/mp4;base64,")


def test_25_allows_longer_videos_than_20():
    # 20 s at 24 fps is fine for 2.5 (30 s cap) but not for 2.0 (15 s cap).
    frames = 24 * 20
    uri = nodes_video._normalize_video(_video(b"x", frames=frames), 0, MODELS["seedance_2_5"])
    assert uri.startswith("data:video/mp4;base64,")
    with pytest.raises(ValueError):
        nodes_video._normalize_video(_video(b"x", frames=frames), 0, MODELS["seedance_2_0"])


# ------------------------------------------------------------- strings


def test_string_reference_passes_through():
    """An asset:// id or a public URL is used as-is."""
    assert nodes_video._normalize_video("asset://asset-1", 0, MODELS["seedance_2_5"]) == "asset://asset-1"
    url = "https://example.com/a.mp4"
    assert nodes_video._normalize_video(url, 0, MODELS["seedance_2_5"]) == url


# --------------------------------------------------------------- schema


def test_video_slot_accepts_video_and_string():
    from comfy_api.latest import io

    schema = nodes_video.ArkSDSeedance25.define_schema()
    slot = next(i for i in schema.inputs if i.id == "reference_videos")
    io_type = slot.template.input.get_io_type()
    assert "VIDEO" in io_type
    assert "STRING" in io_type
