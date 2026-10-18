import pytest
from comfy_api.latest import io
from nodes import nodes_video
from nodes.constants import MODELS


def test_build_body_minimal():
    body = nodes_video.build_body(MODELS["seedance_2_0"], {
        "prompt": "a cat", "resolution": "720p", "ratio": "adaptive",
        "duration": 5, "seed": -1, "watermark": False, "generate_audio": True,
        "images": [], "videos": [], "audios": [],
    })
    assert body["model"] == "doubao-seedance-2-0-260128"
    assert body["resolution"] == "720p"
    assert body["duration"] == 5
    assert "output_format" not in body
    assert "draft" not in body


def test_build_body_25_only_params():
    body = nodes_video.build_body(MODELS["seedance_2_5"], {
        "prompt": "a cat", "resolution": "720p", "ratio": "adaptive",
        "duration": 5, "seed": -1, "watermark": False, "generate_audio": True,
        "images": [], "videos": [], "audios": [],
        "output_format": "mov", "draft": True, "omni_reference_task_type": "reference",
        "priority": 3,
    })
    assert body["output_format"] == "mov"
    assert body["draft"] is True
    assert body["omni_reference_task_type"] == "reference"
    assert body["priority"] == 3


def test_build_body_draft_forces_480p():
    body = nodes_video.build_body(MODELS["seedance_2_5"], {
        "prompt": "a cat", "resolution": "1080p", "ratio": "adaptive",
        "duration": 5, "seed": -1, "watermark": False, "generate_audio": True,
        "images": [], "videos": [], "audios": [], "draft": True,
    })
    assert body["resolution"] == "480p"


def test_collect_references_orders_by_index():
    images = {"reference_image_0": "a", "reference_image_2": "c", "reference_image_1": "b"}
    imgs, vids, auds = nodes_video.collect_references(images, {}, {})
    assert imgs == ["a", "b", "c"]


def test_collect_references_skips_none():
    images = {"reference_image_0": "a", "reference_image_1": None}
    imgs, _, _ = nodes_video.collect_references(images, {}, {})
    assert imgs == ["a"]


def test_reference_slot_types_are_multitype():
    schema = nodes_video.ArkSDSeedance25.define_schema()
    by_id = {i.id: i for i in schema.inputs}
    image_template = by_id["reference_images"].template.input
    assert isinstance(image_template, io.MultiType.Input)
    assert "IMAGE" in image_template.get_io_type()
    assert "STRING" in image_template.get_io_type()
    video_template = by_id["reference_videos"].template.input
    assert isinstance(video_template, io.MultiType.Input)
    assert "VIDEO" in video_template.get_io_type()
    assert "STRING" in video_template.get_io_type()
    assert by_id["reference_audios"].template.input.get_io_type() == "STRING"


def test_autogrow_maxima_match_model():
    schema = nodes_video.ArkSDSeedance25.define_schema()
    by_id = {i.id: i for i in schema.inputs}
    assert by_id["reference_images"].template.max == 30
    assert by_id["reference_videos"].template.max == 10
    assert by_id["reference_audios"].template.max == 10
    schema20 = nodes_video.ArkSDSeedance20.define_schema()
    by_id20 = {i.id: i for i in schema20.inputs}
    assert by_id20["reference_images"].template.max == 9
    assert by_id20["reference_videos"].template.max == 3
    assert by_id20["reference_audios"].template.max == 3
