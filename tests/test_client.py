import pytest
from nodes import client


def test_build_content_text_only():
    content = client.build_content("a cat", [], [], [])
    assert content == [{"type": "text", "text": "a cat"}]


def test_build_content_roles():
    content = client.build_content(
        "p",
        ["data:image/png;base64,AAA"],
        ["asset://asset-1"],
        ["https://x/a.mp3"],
    )
    assert content[1] == {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAA"}, "role": "reference_image"}
    assert content[2] == {"type": "video_url", "video_url": {"url": "asset://asset-1"}, "role": "reference_video"}
    assert content[3] == {"type": "audio_url", "audio_url": {"url": "https://x/a.mp3"}, "role": "reference_audio"}


def test_build_content_omits_empty_prompt():
    content = client.build_content("", ["data:image/png;base64,AAA"], [], [])
    assert content[0]["type"] == "image_url"


def test_ark_error_from_response():
    err = client.ArkError.from_response(400, {"error": {"code": "ModelNotOpen", "message": "not open"}})
    assert err.code == "ModelNotOpen"
    assert "doubao-seedance" in err.hint or "console" in err.hint
