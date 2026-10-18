"""return_last_frame must actually produce a last_frame output."""

from nodes import nodes_video


def _outputs(node_cls):
    schema = node_cls.define_schema()
    return [o.id for o in schema.outputs]


def test_generation_nodes_expose_last_frame_output():
    for node_cls in (
        nodes_video.ArkSDSeedance25,
        nodes_video.ArkSDSeedance20,
        nodes_video.ArkSDSeedance20Fast,
        nodes_video.ArkSDSeedance20Mini,
    ):
        assert "last_frame" in _outputs(node_cls), node_cls.__name__
