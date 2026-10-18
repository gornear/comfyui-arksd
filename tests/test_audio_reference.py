"""Local AUDIO references: encode to WAV, then apply Ark's size and duration caps.

ComfyUI's AUDIO type is an in-memory waveform, not a file, so any source format
has already been decoded by the loading node. The only work here is encoding it
to WAV and refusing payloads Ark would reject anyway.
"""

import base64
import io
import wave

import pytest
import torch

from nodes import nodes_video
from nodes.constants import MODELS


def _audio(seconds: float, rate: int = 16000, channels: int = 1):
    samples = int(rate * seconds)
    return {"waveform": torch.zeros(1, channels, samples), "sampler_rate": rate}


def _decode_wav(data_uri: str) -> wave.Wave_read:
    payload = base64.b64decode(data_uri.split(",", 1)[1])
    return wave.open(io.BytesIO(payload), "rb")


# ------------------------------------------------------------ encoding


def test_audio_becomes_wav_data_uri():
    uri = nodes_video._normalize_audio(_audio(2.0), 0, MODELS["seedance_2_5"])
    assert uri.startswith("data:audio/wav;base64,")


def test_encoded_wav_has_the_right_shape():
    uri = nodes_video._normalize_audio(_audio(2.0, rate=16000, channels=2), 0, MODELS["seedance_2_5"])
    with _decode_wav(uri) as handle:
        assert handle.getframerate() == 16000
        assert handle.getnchannels() == 2
        assert handle.getsampwidth() == 2
        assert handle.getnframes() == 32000


def test_float_waveform_is_scaled_not_truncated():
    """A 0-1 float tensor must become full-scale 16-bit PCM, not zeros."""
    audio = {"waveform": torch.ones(1, 1, 1600) * 0.5, "sampler_rate": 16000}
    uri = nodes_video._normalize_audio(audio, 0, MODELS["seedance_2_5"])
    with _decode_wav(uri) as handle:
        first = handle.readframes(1)
    assert first != b"\x00\x00"


# --------------------------------------------------------------- gates


def test_audio_over_duration_is_refused():
    with pytest.raises(ValueError) as exc:
        nodes_video._normalize_audio(_audio(16.0), 0, MODELS["seedance_2_0"])
    assert "15" in str(exc.value)


def test_25_allows_longer_audio_than_20():
    uri = nodes_video._normalize_audio(_audio(20.0), 0, MODELS["seedance_2_5"])
    assert uri.startswith("data:audio/wav;base64,")
    with pytest.raises(ValueError):
        nodes_video._normalize_audio(_audio(20.0), 0, MODELS["seedance_2_0"])


def test_audio_over_size_is_refused(monkeypatch):
    monkeypatch.setattr(nodes_video, "AUDIO_MAX_BYTES", 1024)
    with pytest.raises(ValueError) as exc:
        nodes_video._normalize_audio(_audio(2.0), 0, MODELS["seedance_2_5"])
    assert "MB" in str(exc.value)


# ------------------------------------------------------------- strings


def test_string_reference_passes_through():
    assert nodes_video._normalize_audio("asset://a1", 0, MODELS["seedance_2_5"]) == "asset://a1"
    url = "https://example.com/a.mp3"
    assert nodes_video._normalize_audio(url, 0, MODELS["seedance_2_5"]) == url


# --------------------------------------------------------------- schema


def test_audio_slot_accepts_audio_and_string():
    from comfy_api.latest import io

    schema = nodes_video.ArkSDSeedance25.define_schema()
    slot = next(i for i in schema.inputs if i.id == "reference_audios")
    io_type = slot.template.input.get_io_type()
    assert "AUDIO" in io_type
    assert "STRING" in io_type


def test_accepts_sample_rate_key_from_load_audio():
    """LoadAudio emits `sample_rate` even though io.Audio declares `sampler_rate`."""
    audio = {"waveform": torch.zeros(1, 1, 16000), "sample_rate": 16000}
    uri = nodes_video._normalize_audio(audio, 0, MODELS["seedance_2_5"])
    with _decode_wav(uri) as handle:
        assert handle.getframerate() == 16000


def test_accepts_sampler_rate_key():
    audio = {"waveform": torch.zeros(1, 1, 16000), "sampler_rate": 16000}
    uri = nodes_video._normalize_audio(audio, 0, MODELS["seedance_2_5"])
    with _decode_wav(uri) as handle:
        assert handle.getframerate() == 16000
