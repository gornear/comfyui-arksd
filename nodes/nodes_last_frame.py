"""The ArkSD Last Frame node.

Takes a VIDEO and emits its final frame as an image, so one clip's ending can
start the next one. Only the tail of the video is decoded; see ``video_utils``.
"""

from comfy_api.latest import io

from . import video_utils


def _video_bytes(video) -> bytes:
    """Read the raw bytes of a VIDEO, avoiding a full decode into tensors."""
    source = video.get_stream_source()
    if hasattr(source, "read"):
        return source.read()
    with open(source, "rb") as handle:
        return handle.read()


class ArkSDLastFrame(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="ArkSD_LastFrame",
            display_name="ArkSD Last Frame",
            category="api node/ArkSD",
            description=(
                "Extract the last frame of a video without decoding the whole thing. "
                "Chain one clip's last frame into the next clip's first frame."
            ),
            inputs=[
                io.Video.Input(
                    "video",
                    tooltip="The video to read the last frame from.",
                ),
            ],
            outputs=[
                io.Image.Output("image", tooltip="The last frame, as a one-image batch."),
            ],
        )

    @classmethod
    def execute(cls, video) -> io.NodeOutput:
        data = _video_bytes(video)
        return io.NodeOutput(video_utils.extract_last_frame(data))
