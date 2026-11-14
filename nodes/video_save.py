"""Write a VIDEO to disk with a user-chosen audio codec.

ComfyUI's own ``VideoInput.save_to`` hardcodes the audio stream to aac (or opus
for webm), so there is no way to keep a lossless soundtrack through the official
output nodes. This writes the container itself with PyAV.
"""

import json
import logging
import math
import os
from fractions import Fraction

import av
import folder_paths

from comfy.cli_args import args
from comfy_api.latest import io, ui

from .video_utils import AV1_ENCODERS, H264_ENCODERS, PRESETS, pick_video_encoder, video_encoder_options

LOGGER = logging.getLogger("arksd")

AUDIO_ENCODERS = {"flac": "flac", "mp3": "libmp3lame", "aac": "aac"}

AUDIO_LAYOUTS = {1: "mono", 2: "stereo", 6: "5.1"}


def write_video(
    path: str,
    components,
    container: str,
    video_codec: str,
    preset: str,
    crf: int,
    audio_codec: str,
    audio_quality: str,
    metadata: dict | None = None,
) -> None:
    """Encode ``components`` into ``path``."""
    open_kwargs = {"mode": "w", "format": "mp4" if container == "mp4" else "matroska"}
    if container == "mp4":
        # Without this ffmpeg drops non-standard metadata tags from isobmff.
        open_kwargs["options"] = {"movflags": "use_metadata_tags"}

    candidates = H264_ENCODERS if video_codec == "h264" else AV1_ENCODERS
    encoder = pick_video_encoder(candidates)
    if encoder is None:
        encoder = candidates[-1]
        LOGGER.info("[ArkSD] no hardware encoder available, saving with %s", encoder)

    images = components.images
    frame_count, height, width = images.shape[:3]
    frame_rate = Fraction(round(components.frame_rate * 1000), 1000)

    with av.open(path, **open_kwargs) as out:
        if metadata:
            for key, value in metadata.items():
                out.metadata[key] = value if isinstance(value, str) else json.dumps(value)

        video_stream = out.add_stream(encoder, rate=frame_rate)
        video_stream.width = width
        video_stream.height = height
        video_stream.pix_fmt = "yuv420p"
        video_stream.options = video_encoder_options(encoder, crf, preset)

        audio_stream = _add_audio_stream(out, components.audio, audio_codec, audio_quality)

        # isobmff containers reject video-then-audio muxing without rebasing
        # timestamps, so the audio goes in first with an explicit pts.
        if audio_stream is not None:
            _write_audio(out, audio_stream, components.audio, frame_rate, frame_count)

        for index in range(frame_count):
            array = (images[index].clamp(0, 1) * 255).byte().cpu().numpy()
            frame = av.VideoFrame.from_ndarray(array, format="rgb24")
            frame.pts = index
            frame = frame.reformat(format="yuv420p")
            for packet in video_stream.encode(frame):
                out.mux(packet)
        for packet in video_stream.encode(None):
            out.mux(packet)


def _add_audio_stream(out, audio, audio_codec, audio_quality):
    """Add the audio stream, or return None when the video has no audio."""
    if audio is None:
        return None
    sample_rate = int(audio["sample_rate"])
    channels = audio["waveform"].shape[1]
    layout = AUDIO_LAYOUTS.get(channels, "stereo")
    stream = out.add_stream(AUDIO_ENCODERS[audio_codec], rate=sample_rate, layout=layout)
    if audio_codec == "mp3":
        if audio_quality == "V0":
            stream.codec_context.qscale = 1
        else:
            stream.bit_rate = int(audio_quality.rstrip("k")) * 1000
    return stream


def _write_audio(out, stream, audio, frame_rate, frame_count):
    """Write the whole audio track, trimmed to the video's duration."""
    sample_rate = int(audio["sample_rate"])
    channels = audio["waveform"].shape[1]
    layout = AUDIO_LAYOUTS.get(channels, "stereo")
    samples = math.ceil(sample_rate / frame_rate * frame_count)
    waveform = audio["waveform"][0, :, :samples]

    frame = av.AudioFrame.from_ndarray(waveform.contiguous().numpy(), format="fltp", layout=layout)
    frame.sample_rate = sample_rate
    frame.pts = 0
    for packet in stream.encode(frame):
        out.mux(packet)
    for packet in stream.encode(None):
        out.mux(packet)


class ArkSD_SaveVideo(io.ComfyNode):
    """Save a video, choosing the audio codec instead of always getting aac."""

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="ArkSD_SaveVideo",
            display_name="ArkSD Save Video",
            category="api node/ArkSD",
            description=(
                "Save a video to the output directory with a selectable audio codec. "
                "The official Save Video node always writes aac, so a lossless track cannot survive it."
            ),
            inputs=[
                io.Video.Input("video", tooltip="The video to save."),
                io.String.Input(
                    "filename_prefix",
                    default="video/ArkSD",
                    tooltip="The prefix for the file to save. May include formatting tokens such as %date:yyyy-MM-dd%.",
                ),
                io.Combo.Input(
                    "container",
                    options=["mp4", "mkv"],
                    default="mp4",
                    tooltip="Both containers carry every audio codec on offer.",
                ),
                io.Combo.Input(
                    "video_codec",
                    options=["h264", "av1"],
                    default="h264",
                    tooltip="h264 is the safe choice; av1 is smaller at the same quality but slower to encode.",
                ),
                io.Combo.Input(
                    "preset",
                    options=PRESETS,
                    default="medium",
                    tooltip="Faster presets encode quickly and produce larger files.",
                ),
                io.Int.Input(
                    "crf",
                    default=23,
                    min=0,
                    max=51,
                    tooltip="Lower keeps more detail and makes a larger file. Used for both hardware and software encoding.",
                ),
                io.DynamicCombo.Input(
                    "audio_codec",
                    options=[
                        io.DynamicCombo.Option("flac", []),
                        io.DynamicCombo.Option(
                            "mp3",
                            [
                                io.Combo.Input(
                                    "quality",
                                    options=["V0", "128k", "320k"],
                                    default="V0",
                                    tooltip="V0 is variable bitrate at about 245 kbps; the others are constant bitrate.",
                                ),
                            ],
                        ),
                        io.DynamicCombo.Option("aac", []),
                    ],
                    tooltip="flac is lossless, mp3 and aac are lossy. flac is saved at 16-bit.",
                ),
            ],
            hidden=[io.Hidden.prompt, io.Hidden.extra_pnginfo],
            is_output_node=True,
            outputs=[io.Video.Output("video", tooltip="The input video, unchanged.")],
        )

    @staticmethod
    def resolve_save_args(audio_codec) -> tuple[str, str]:
        """Return the chosen codec and quality from the dynamic combo value."""
        if isinstance(audio_codec, dict):
            return audio_codec.get("audio_codec", "flac"), audio_codec.get("quality", "V0")
        return audio_codec, "V0"

    @classmethod
    def execute(cls, video, filename_prefix, container, video_codec, preset, crf, audio_codec) -> io.NodeOutput:
        codec, quality = cls.resolve_save_args(audio_codec)
        width, height = video.get_dimensions()
        full_output_folder, filename, counter, subfolder, _ = folder_paths.get_save_image_path(
            filename_prefix,
            folder_paths.get_output_directory(),
            width,
            height,
        )

        metadata = None
        if not args.disable_metadata:
            hidden = cls.hidden
            collected = {}
            if hidden is not None:
                if hidden.extra_pnginfo is not None:
                    collected.update(hidden.extra_pnginfo)
                if hidden.prompt is not None:
                    collected["prompt"] = hidden.prompt
            metadata = collected or None

        file = f"{filename}_{counter:05}_.{container}"
        write_video(
            os.path.join(full_output_folder, file),
            video.get_components(),
            container=container,
            video_codec=video_codec,
            preset=preset,
            crf=crf,
            audio_codec=codec,
            audio_quality=quality,
            metadata=metadata,
        )
        return io.NodeOutput(video, ui=ui.PreviewVideo([ui.SavedResult(file, subfolder, io.FolderType.output)]))
