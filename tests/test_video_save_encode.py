"""The save-video node must honour the audio codec the user picked."""

import numpy as np
import pytest
import torch
from fractions import Fraction

import av

from comfy_api.latest._util import VideoComponents
from nodes import video_save


def _components(frames=24, size=256, fps=24, audio=True, audio_scale=1.0):
    images = torch.zeros((frames, size, size, 3))
    images[..., 0] = torch.linspace(0, 1, frames)[:, None, None]
    payload = None
    if audio:
        sample_rate = 44100
        samples = int(sample_rate / fps * frames * audio_scale)
        wave = torch.zeros((1, 2, samples))
        wave[0, 0] = torch.sin(torch.linspace(0, 400, samples))
        payload = {"waveform": wave, "sample_rate": sample_rate}
    return VideoComponents(images=images, frame_rate=Fraction(fps), audio=payload)


def _audio_codec_of(path):
    with av.open(str(path)) as container:
        return [stream.codec_context.name for stream in container.streams.audio]


@pytest.mark.parametrize("container,ext", [("mp4", "mp4"), ("mkv", "mkv")])
@pytest.mark.parametrize("audio_codec,expected", [
    ("flac", "flac"),
    ("mp3", "mp3float"),
    ("aac", "aac"),
])
def test_every_container_audio_combination_writes_a_readable_file(tmp_path, container, ext, audio_codec, expected):
    path = tmp_path / f"out.{ext}"
    video_save.write_video(
        str(path),
        _components(),
        container=container,
        video_codec="h264",
        preset="fastest",
        crf=23,
        audio_codec=audio_codec,
        audio_quality="V0",
    )
    assert path.stat().st_size > 0
    assert _audio_codec_of(path) == [expected]


def test_video_without_audio_still_writes(tmp_path):
    path = tmp_path / "silent.mp4"
    video_save.write_video(
        str(path),
        _components(audio=False),
        container="mp4", video_codec="h264", preset="fastest", crf=23,
        audio_codec="flac", audio_quality="V0",
    )
    assert _audio_codec_of(path) == []


def test_audio_is_truncated_to_the_video_duration(tmp_path):
    path = tmp_path / "long_audio.mp4"
    # Audio twice as long as the video.
    video_save.write_video(
        str(path),
        _components(frames=24, fps=24, audio_scale=2.0),
        container="mp4", video_codec="h264", preset="fastest", crf=23,
        audio_codec="aac", audio_quality="V0",
    )
    with av.open(str(path)) as container:
        audio = container.streams.audio[0]
        video = container.streams.video[0]
        audio_seconds = float(audio.duration * audio.time_base)
        video_seconds = float(video.duration * video.time_base)
    assert audio_seconds <= video_seconds + 0.2


def test_metadata_survives_the_mp4_write(tmp_path):
    path = tmp_path / "tagged.mp4"
    video_save.write_video(
        str(path),
        _components(audio=False),
        container="mp4", video_codec="h264", preset="fastest", crf=23,
        audio_codec="flac", audio_quality="V0",
        metadata={"prompt": '{"1": {}}'},
    )
    with av.open(str(path)) as container:
        assert container.metadata.get("prompt") == '{"1": {}}'


def test_missing_hardware_encoder_falls_back_to_software(tmp_path, monkeypatch):
    seen = {}
    real = video_save.pick_video_encoder

    def no_nvenc(candidates):
        seen["candidates"] = candidates
        return real([name for name in candidates if "_nvenc" not in name])

    monkeypatch.setattr(video_save, "pick_video_encoder", no_nvenc)
    path = tmp_path / "fallback.mp4"
    video_save.write_video(
        str(path),
        _components(audio=False),
        container="mp4", video_codec="h264", preset="fastest", crf=23,
        audio_codec="flac", audio_quality="V0",
    )
    assert seen["candidates"][0] == "h264_nvenc"
    assert path.stat().st_size > 0
    with av.open(str(path)) as container:
        assert container.streams.video[0].codec_context.name == "h264"
