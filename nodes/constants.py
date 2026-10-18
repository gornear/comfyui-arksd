"""Static model capability table and shared limits for ArkSD nodes.

The Ark API has no endpoint that reports which models an account has opened,
so the node schemas are driven by this table instead. Values are taken from
the official Seedance 2.5 and Seedance 2.0 documentation.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelSpec:
    """Capabilities and limits for one Seedance model."""

    model_id: str
    resolutions: list[str]
    default_resolution: str
    duration_min: int
    duration_max: int
    duration_default: int
    max_images: int
    max_videos: int
    max_audios: int
    supports_output_format: bool
    supports_draft: bool
    supports_task_type: bool


MODELS: dict[str, ModelSpec] = {
    "seedance_2_5": ModelSpec(
        model_id="doubao-seedance-2-5-260628",
        resolutions=["480p", "720p", "1080p"],
        default_resolution="720p",
        duration_min=4,
        duration_max=30,
        duration_default=-1,
        max_images=30,
        max_videos=10,
        max_audios=10,
        supports_output_format=True,
        supports_draft=True,
        supports_task_type=True,
    ),
    "seedance_2_0": ModelSpec(
        model_id="doubao-seedance-2-0-260128",
        resolutions=["480p", "720p", "1080p", "4k"],
        default_resolution="720p",
        duration_min=4,
        duration_max=15,
        duration_default=-1,
        max_images=9,
        max_videos=3,
        max_audios=3,
        supports_output_format=False,
        supports_draft=False,
        supports_task_type=False,
    ),
    "seedance_2_0_fast": ModelSpec(
        model_id="doubao-seedance-2-0-fast-260128",
        resolutions=["480p", "720p"],
        default_resolution="720p",
        duration_min=4,
        duration_max=15,
        duration_default=-1,
        max_images=9,
        max_videos=3,
        max_audios=3,
        supports_output_format=False,
        supports_draft=False,
        supports_task_type=False,
    ),
    "seedance_2_0_mini": ModelSpec(
        model_id="doubao-seedance-2-0-mini-260615",
        resolutions=["480p", "720p"],
        default_resolution="720p",
        duration_min=4,
        duration_max=15,
        duration_default=-1,
        max_images=9,
        max_videos=3,
        max_audios=3,
        supports_output_format=False,
        supports_draft=False,
        supports_task_type=False,
    ),
}

# Aspect ratios accepted by every Seedance 2.x model.
RATIOS = ["adaptive", "16:9", "4:3", "1:1", "3:4", "9:16", "21:9"]

# Ark limits for a single reference image.
IMAGE_MAX_BYTES = 30 * 1024 * 1024
IMAGE_MIN_EDGE = 300
IMAGE_MAX_EDGE = 6000
IMAGE_MIN_RATIO = 0.4
IMAGE_MAX_RATIO = 2.5

# Ark limits for the whole request body.
REQUEST_MAX_BYTES = 64 * 1024 * 1024

# A reference video sent inline as base64 must leave room in the 64 MB request
# body for the rest of the payload, so it is capped at 30 MB.
VIDEO_MAX_BYTES = 30 * 1024 * 1024

# Container Ark assumes for an inline video. Ark accepts mp4 and mov.
VIDEO_MIME = "video/mp4"

# Ark caps a single reference audio at 15 MB. An in-memory waveform is encoded
# as uncompressed WAV, so this binds sooner than it does for video.
AUDIO_MAX_BYTES = 15 * 1024 * 1024
AUDIO_MIME = "audio/wav"
AUDIO_SAMPLE_WIDTH = 2  # 16-bit PCM

# Task polling defaults.
DEFAULT_TIMEOUT = 1800
MIN_TIMEOUT = 300
MAX_TIMEOUT = 86400
DEFAULT_POLL_INTERVAL = 10.0

# Asset list cache lifetime, in seconds.
ASSET_CACHE_TTL = 300

# Seed range accepted by the API.
SEED_MIN = -1
SEED_MAX = 2147483647

# Task expiry threshold accepted by the API.
EXPIRES_MIN = 3600
EXPIRES_MAX = 259200
EXPIRES_DEFAULT = 172800

# Execution priority accepted by the API.
PRIORITY_MIN = 0
PRIORITY_MAX = 9

# Draft mode always produces 480p; the final pass is always 1080p.
DRAFT_RESOLUTION = "480p"
DRAFT_FINAL_RESOLUTION = "1080p"
