"""ArkSD Last Frame: pull the last frame out of a video without full decode.

Chaining one clip's last frame into the next clip's first frame is the main use
case, so the node must not decode the whole file.
"""

import io

import av
import numpy as np
import pytest
import torch

from nodes import nodes_last_frame, video_utils


def _make_video(path, frames: int = 30, size: int = 32, fps: int = 24, value_step: int = 8):
    with av.open(str(path), mode="w") as container:
        stream = container.add_stream("h264", rate=fps)
        stream.width = size
        stream.height = size
        stream.pix_fmt = "yuv420p"
        for index in range(frames):
            colour = min(255, index * value_step)
            array = np.full((size, size, 3), colour, dtype=np.uint8)
            frame = av.VideoFrame.from_ndarray(array, format="rgb24")
            for packet in stream.encode(frame):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)


@pytest.fixture(scope="module")
def video_bytes(tmp_path_factory):
    path = tmp_path_factory.mktemp("videos") / "clip.mp4"
    _make_video(path)
    return path.read_bytes()


# ------------------------------------------------------------- extraction


def test_extract_returns_a_single_frame_batch(video_bytes):
    frame = video_utils.extract_last_frame(video_bytes)
    assert frame.shape[0] == 1
    assert frame.shape[-1] == 3
    assert frame.dtype == torch.float32


def test_extracted_frame_is_in_unit_range(video_bytes):
    frame = video_utils.extract_last_frame(video_bytes)
    assert float(frame.min()) >= 0.0
    assert float(frame.max()) <= 1.0


def test_extract_returns_the_actual_last_frame(tmp_path):
    """The final frame is the brightest one, so its value proves the seek worked."""
    path = tmp_path / "ramp.mp4"
    _make_video(path, frames=30, value_step=8)
    frame = video_utils.extract_last_frame(path.read_bytes())
    # 29 * 8 = 232, i.e. ~0.91 after the 0-1 conversion.
    assert float(frame.mean()) > 0.8


def test_undecodable_bytes_raise_a_clear_error():
    with pytest.raises(ValueError) as exc:
        video_utils.extract_last_frame(b"not a video")
    assert "decode" in str(exc.value).lower()


# ------------------------------------------------------------------- node


def test_node_schema():
    schema = nodes_last_frame.ArkSDLastFrame.define_schema()
    assert schema.node_id == "ArkSD_LastFrame"
    assert schema.category == "api node/ArkSD"
    assert [i.id for i in schema.inputs] == ["video"]
    assert [o.id for o in schema.outputs] == ["image"]


def test_node_reads_bytes_without_decoding_the_whole_video(video_bytes):
    class FakeVideo:
        def __init__(self, payload):
            self._payload = payload
            self.stream_calls = 0

        def get_stream_source(self):
            self.stream_calls += 1
            return io.BytesIO(self._payload)

        def get_components(self):
            raise AssertionError("must not decode the whole video")

    video = FakeVideo(video_bytes)
    result = nodes_last_frame.ArkSDLastFrame.execute(video)
    assert video.stream_calls == 1
    assert result.args[0].shape[0] == 1


def test_node_accepts_a_path_source(tmp_path):
    path = tmp_path / "clip.mp4"
    _make_video(path)

    class PathVideo:
        def get_stream_source(self):
            return str(path)

    result = nodes_last_frame.ArkSDLastFrame.execute(PathVideo())
    assert result.args[0].shape[0] == 1
