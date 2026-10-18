"""Reference image normalization for the Ark API.

Ark accepts a reference image as a public URL, an ``asset://`` id, or a base64
data URL. A ComfyUI ``IMAGE`` tensor has to become the last of those, and it
has to satisfy Ark's limits:

* single image <= 30 MB
* aspect ratio (w/h) in [0.4, 2.5]
* single edge in [300, 6000] px

A ``LoadImage`` output can easily break those, so instead of rejecting the
workflow the image is scaled and re-encoded until it fits. Every adjustment is
logged so the user can see what happened.
"""

import base64
import io
import logging

import torch
from PIL import Image

from .constants import (
    IMAGE_MAX_BYTES,
    IMAGE_MAX_EDGE,
    IMAGE_MAX_RATIO,
    IMAGE_MIN_EDGE,
    IMAGE_MIN_RATIO,
)

LOGGER = logging.getLogger("arksd")


def tensor_to_pil(tensor) -> Image.Image:
    """Convert a ComfyUI ``[1, H, W, 3]`` float tensor in 0-1 to a PIL image."""
    frame = tensor[0] if tensor.dim() == 4 else tensor
    frame = frame.clamp(0.0, 1.0).mul(255.0).round().to("cpu", torch.uint8)
    return Image.fromarray(frame.numpy(), mode="RGB")


def _scale_to_limits(width: int, height: int) -> tuple[int, int]:
    """Return the largest size within Ark's edge and aspect ratio limits."""
    scale = 1.0
    longest = max(width, height)
    shortest = min(width, height)
    if longest > IMAGE_MAX_EDGE:
        scale = min(scale, IMAGE_MAX_EDGE / longest)
    if shortest * scale < IMAGE_MIN_EDGE:
        scale = max(scale, IMAGE_MIN_EDGE / shortest)
    ratio = width / height
    if ratio > IMAGE_MAX_RATIO:
        scale = min(scale, IMAGE_MAX_RATIO / ratio)
    elif ratio < IMAGE_MIN_RATIO:
        scale = min(scale, ratio / IMAGE_MIN_RATIO)
    new_w = max(IMAGE_MIN_EDGE, min(IMAGE_MAX_EDGE, int(round(width * scale))))
    new_h = max(IMAGE_MIN_EDGE, min(IMAGE_MAX_EDGE, int(round(height * scale))))
    return new_w, new_h


def _encode(image: Image.Image, fmt: str) -> bytes:
    buffer = io.BytesIO()
    if fmt == "PNG":
        image.save(buffer, format="PNG", optimize=True)
    else:
        image.save(buffer, format="JPEG", quality=95)
    return buffer.getvalue()


def normalize_image(tensor, label: str) -> str:
    """Return a ``data:image/...;base64,...`` string that Ark will accept."""
    image = tensor_to_pil(tensor)
    width, height = image.size

    new_w, new_h = _scale_to_limits(width, height)
    if (new_w, new_h) != (width, height):
        image = image.resize((new_w, new_h), Image.LANCZOS)
        LOGGER.info(
            "[ArkSD] %s resized %dx%d -> %dx%d (edge/ratio limit)",
            label,
            width,
            height,
            new_w,
            new_h,
        )

    fmt = "PNG"
    payload = _encode(image, fmt)
    if len(payload) > IMAGE_MAX_BYTES:
        fmt = "JPEG"
        payload = _encode(image, fmt)
        LOGGER.info("[ArkSD] %s re-encoded as JPEG (size limit)", label)

    # Keep halving until the payload fits, in case JPEG is still too large.
    while len(payload) > IMAGE_MAX_BYTES:
        width, height = image.size
        new_w = max(IMAGE_MIN_EDGE, width // 2)
        new_h = max(IMAGE_MIN_EDGE, height // 2)
        if (new_w, new_h) == (width, height):
            break
        image = image.resize((new_w, new_h), Image.LANCZOS)
        payload = _encode(image, fmt)
        LOGGER.info(
            "[ArkSD] %s downscaled to %dx%d (size limit)", label, new_w, new_h
        )

    mime = "image/png" if fmt == "PNG" else "image/jpeg"
    encoded = base64.b64encode(payload).decode("ascii")
    return f"data:{mime};base64,{encoded}"
