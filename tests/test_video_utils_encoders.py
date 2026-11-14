"""Encoder probing and preset mapping for the save-video node."""

from nodes import video_utils


def test_preset_tables_cover_every_node_preset():
    assert video_utils.PRESETS == ["fastest", "fast", "medium", "slow", "slowest"]
    for preset in video_utils.PRESETS:
        assert preset in video_utils.X264_PRESET
        assert preset in video_utils.NVENC_PRESET
        assert preset in video_utils.SVT_AV1_PRESET


def test_preset_tables_map_to_the_spec_values():
    assert video_utils.X264_PRESET["fastest"] == "ultrafast"
    assert video_utils.X264_PRESET["medium"] == "medium"
    assert video_utils.X264_PRESET["slowest"] == "veryslow"
    assert video_utils.NVENC_PRESET["fastest"] == "p1"
    assert video_utils.NVENC_PRESET["fast"] == "p3"
    assert video_utils.NVENC_PRESET["medium"] == "p4"
    assert video_utils.NVENC_PRESET["slow"] == "p6"
    assert video_utils.NVENC_PRESET["slowest"] == "p7"


def test_pick_video_encoder_returns_first_available():
    assert video_utils.pick_video_encoder(["libx264"]) == "libx264"


def test_pick_video_encoder_returns_none_when_nothing_is_available():
    assert video_utils.pick_video_encoder(["definitely_not_an_encoder"]) is None


def test_software_encoder_options_use_crf_and_preset_name():
    options = video_utils.video_encoder_options("libx264", 23, "medium")
    assert options["crf"] == "23"
    assert options["preset"] == "medium"


def test_nvenc_encoder_options_use_vbr_cq():
    options = video_utils.video_encoder_options("h264_nvenc", 23, "slow")
    assert options["rc"] == "vbr"
    assert options["cq"] == "23"
    assert options["b:v"] == "0"
    assert options["preset"] == "p6"
    assert "qp" not in options


def test_av1_nvenc_encoder_options_match_h264_nvenc_shape():
    options = video_utils.video_encoder_options("av1_nvenc", 30, "fast")
    assert options == {"rc": "vbr", "cq": "30", "b:v": "0", "preset": "p3"}
