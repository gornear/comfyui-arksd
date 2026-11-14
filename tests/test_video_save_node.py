"""Schema and argument handling for the ArkSD Save Video node."""

import av
import numpy as np
import torch
from fractions import Fraction

from comfy_api.latest._util import VideoComponents
from nodes.video_save import ArkSD_SaveVideo


def test_node_is_registered():
    import importlib.util
    import sys
    from pathlib import Path

    # The repo directory has a hyphen in its name, so it cannot be imported as
    # a package path. ComfyUI loads it under a valid name; mirror that by giving
    # the spec a search location, which is what makes the relative imports work.
    root = Path(__file__).resolve().parent.parent
    spec = importlib.util.spec_from_file_location(
        "arksd_package", root / "__init__.py", submodule_search_locations=[str(root)]
    )
    package = importlib.util.module_from_spec(spec)
    sys.modules["arksd_package"] = package
    spec.loader.exec_module(package)
    registered = package.NODE_CLASS_MAPPINGS["ArkSD_SaveVideo"]
    # The package loads its own copy of the module, so compare names not identity.
    assert registered.__name__ == ArkSD_SaveVideo.__name__
    assert package.NODE_DISPLAY_NAME_MAPPINGS["ArkSD_SaveVideo"] == "ArkSD Save Video"


def test_schema_offers_the_spec_combos():
    schema = ArkSD_SaveVideo.define_schema()
    by_id = {entry.id: entry for entry in schema.inputs}
    assert by_id["container"].options == ["mp4", "mkv"]
    assert by_id["video_codec"].options == ["h264", "av1"]
    assert by_id["preset"].options == ["fastest", "fast", "medium", "slow", "slowest"]
    assert by_id["preset"].default == "medium"
    assert by_id["crf"].default == 23


def test_audio_quality_only_appears_for_mp3():
    schema = ArkSD_SaveVideo.define_schema()
    by_id = {entry.id: entry for entry in schema.inputs}
    options = {option.key: option for option in by_id["audio_codec"].options}
    assert list(options) == ["flac", "mp3", "aac"]
    assert options["mp3"].inputs, "mp3 must carry the quality input"
    assert options["flac"].inputs == []
    assert options["aac"].inputs == []
    quality = options["mp3"].inputs[0]
    assert quality.id == "quality"
    assert quality.options == ["V0", "128k", "320k"]
    assert quality.default == "V0"


def test_resolve_save_args_reads_the_dynamic_combo_dict():
    assert ArkSD_SaveVideo.resolve_save_args({"audio_codec": "mp3", "quality": "128k"}) == ("mp3", "128k")
    assert ArkSD_SaveVideo.resolve_save_args({"audio_codec": "flac"}) == ("flac", "V0")


def test_execute_returns_the_input_video_and_writes_the_file(tmp_path, monkeypatch):
    import folder_paths
    monkeypatch.setattr(folder_paths, "get_output_directory", lambda: str(tmp_path))
    images = torch.zeros((12, 32, 32, 3))
    components = VideoComponents(images=images, frame_rate=Fraction(24))
    calls = {}

    class FakeVideo:
        def get_components(self):
            return components

        def get_dimensions(self):
            return 32, 32

    def fake_write(path, comp, **kwargs):
        calls.update(kwargs)
        with open(path, "wb") as handle:
            handle.write(b"x")

    monkeypatch.setattr("nodes.video_save.write_video", fake_write)
    video = FakeVideo()
    output = ArkSD_SaveVideo.execute(
        video, "video/test", "mkv", "h264", "medium", 23, {"audio_codec": "flac"},
    )
    assert output.args[0] is video
    assert calls["container"] == "mkv"
    assert calls["audio_codec"] == "flac"
    assert (tmp_path / "video").is_dir()
