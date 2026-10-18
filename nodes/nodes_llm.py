"""ArkSD LLM and ArkSD Texts nodes.

ArkSD LLM calls the Ark chat completions endpoint and returns text. It keeps
the behavior of the reference customLLM node (multi-image input, sampling
parameters, automatic image downscaling) but drops the api_url and api_key
widgets: the endpoint is fixed to Ark and the credential comes from
api_keys.json through the usual ``api_key_name`` combo, so no secret ever
lands in a workflow file.

ArkSD Texts concatenates up to ten text slots into one string.

Both nodes use the V3 schema because ``IO.Autogrow`` can place a group of
inputs at any position in the list, which the V1 INPUT_TYPES dict cannot do.
"""

import base64
import io
import json
import logging

import aiohttp
import numpy as np
from PIL import Image

from comfy_api.latest import io as comfy_io

from . import config

LOGGER = logging.getLogger("arksd")

# Ark's OpenAI-compatible chat completions endpoint.
ARK_CHAT_URL = "https://ark.cn-beijing.volces.com/api/v3/chat/completions"

# Autogrow slot counts.
MAX_IMAGES = 5
MAX_TEXTS = 10

# Used when images are supplied without any text.
FALLBACK_PROMPT = "Describe the image."

# Image downscaling ladder, matching the reference node.
SHRINK_FACTOR = 0.7
MAX_SHRINK_STEPS = 3
FALLBACK_QUALITY_START = 50
FALLBACK_QUALITY_STEP = 5
FALLBACK_QUALITY_MIN = 5
JPEG_MIME = "image/jpeg"


def _tensor_to_pil(tensor) -> Image.Image:
    """Convert a ComfyUI IMAGE tensor [B,H,W,C] in 0-1 to a PIL image."""
    array = tensor.cpu().numpy()
    if array.ndim == 4:
        array = array[0]
    array = np.clip(array * 255.0, 0, 255).astype(np.uint8)
    return Image.fromarray(array)


def _encode_jpeg_b64(image: Image.Image, quality: int) -> str:
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=quality)
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def encode_image_with_limit(tensor, max_side: int, max_kb: int, quality: int) -> str:
    """Encode an IMAGE tensor as a JPEG data URI no larger than ``max_kb``.

    The image is converted to RGB, scaled to ``max_side``, then shrunk up to
    three times and finally had its quality lowered until the base64 payload
    fits. Raising instead would reject a workflow that could have run.
    """
    max_bytes = max_kb * 1024
    image = _tensor_to_pil(tensor)
    if image.mode != "RGB":
        image = image.convert("RGB")

    if max_side and max_side > 0:
        width, height = image.size
        longest = max(width, height)
        if longest > max_side:
            scale = max_side / float(longest)
            image = image.resize(
                (max(1, int(width * scale)), max(1, int(height * scale))),
                Image.LANCZOS,
            )

    encoded = _encode_jpeg_b64(image, quality)
    if len(encoded) < max_bytes:
        return f"data:{JPEG_MIME};base64,{encoded}"

    for _ in range(MAX_SHRINK_STEPS):
        width, height = image.size
        new_size = (max(1, int(width * SHRINK_FACTOR)), max(1, int(height * SHRINK_FACTOR)))
        if new_size == (width, height):
            break
        image = image.resize(new_size, Image.LANCZOS)
        encoded = _encode_jpeg_b64(image, quality)
        if len(encoded) < max_bytes:
            return f"data:{JPEG_MIME};base64,{encoded}"

    current_quality = FALLBACK_QUALITY_START
    while current_quality >= FALLBACK_QUALITY_MIN:
        encoded = _encode_jpeg_b64(image, current_quality)
        if len(encoded) < max_bytes:
            return f"data:{JPEG_MIME};base64,{encoded}"
        current_quality -= FALLBACK_QUALITY_STEP

    raise RuntimeError(
        f"[ArkSD] could not compress the image below {max_kb} KB "
        f"(size {image.size[0]}x{image.size[1]}, quality {FALLBACK_QUALITY_MIN}). "
        f"Lower image_max_side or raise image_max_kb."
    )


class ArkSDLLM(comfy_io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return comfy_io.Schema(
            node_id="ArkSD_LLM",
            display_name="ArkSD LLM",
            category="api node/ArkSD",
            description=(
                "Call Ark's OpenAI-compatible chat completions endpoint and return "
                "the generated text. Supports up to 5 optional images. The API key "
                "is read from api_keys.json."
            ),
            inputs=[
                comfy_io.Combo.Input(
                    "api_key_name",
                    options=config.list_api_key_names() or ["<none>"],
                    tooltip="Which entry of api_keys.json to use.",
                ),
                comfy_io.String.Input(
                    "model",
                    default="doubao-seed-2-0-pro",
                    tooltip="Ark model id or endpoint id. Pick a vision model to use images.",
                ),
                comfy_io.String.Input(
                    "system_prompt",
                    multiline=True,
                    default="You are a helpful assistant.",
                    tooltip="System prompt.",
                ),
                comfy_io.String.Input(
                    "prompt",
                    multiline=True,
                    default="",
                    tooltip=(
                        "User input. If empty while images are connected, it falls "
                        f"back to '{FALLBACK_PROMPT}'."
                    ),
                ),
                comfy_io.Float.Input(
                    "temperature",
                    default=0.0,
                    min=0.0,
                    max=2.0,
                    step=0.01,
                    tooltip="Sampling temperature; higher is more random.",
                ),
                comfy_io.Int.Input(
                    "top_k",
                    default=0,
                    min=0,
                    max=1000,
                    step=1,
                    tooltip="Top-k sampling. 0 means the parameter is not sent.",
                ),
                comfy_io.Float.Input(
                    "top_p",
                    default=0.3,
                    min=0.0,
                    max=1.0,
                    step=0.01,
                    tooltip="Nucleus sampling probability.",
                ),
                comfy_io.Float.Input(
                    "presence_penalty",
                    default=0.0,
                    min=-2.0,
                    max=2.0,
                    step=0.01,
                    tooltip="Positive values encourage new topics.",
                ),
                comfy_io.Float.Input(
                    "frequency_penalty",
                    default=0.0,
                    min=-2.0,
                    max=2.0,
                    step=0.01,
                    tooltip="Positive values reduce repeated wording.",
                ),
                comfy_io.Int.Input(
                    "max_tokens",
                    default=16384,
                    min=1,
                    max=128000,
                    step=1,
                    tooltip="Maximum number of generated tokens.",
                ),
                comfy_io.Int.Input(
                    "timeout",
                    default=60,
                    min=1,
                    max=600,
                    step=1,
                    tooltip="HTTP timeout in seconds.",
                ),
                comfy_io.Autogrow.Input(
                    "images",
                    template=comfy_io.Autogrow.TemplateNames(
                        comfy_io.Image.Input("image"),
                        names=[f"image_{i}" for i in range(1, MAX_IMAGES + 1)],
                        min=0,
                    ),
                    tooltip=f"Optional images, up to {MAX_IMAGES}. Unconnected slots are ignored.",
                ),
                comfy_io.Int.Input(
                    "image_max_side",
                    default=1024,
                    min=0,
                    max=8192,
                    step=64,
                    tooltip="Initial long-edge limit in pixels. 0 disables scaling.",
                ),
                comfy_io.Int.Input(
                    "image_max_kb",
                    default=1024,
                    min=64,
                    max=10240,
                    step=64,
                    tooltip="Per-image base64 size limit in KB. Larger images are shrunk automatically.",
                ),
                comfy_io.Int.Input(
                    "image_quality",
                    default=95,
                    min=1,
                    max=100,
                    step=1,
                    tooltip="Initial JPEG quality. Lowered automatically if the size limit is exceeded.",
                ),
            ],
            outputs=[comfy_io.String.Output("text")],
        )

    @classmethod
    async def execute(
        cls,
        api_key_name,
        model,
        system_prompt,
        prompt,
        temperature,
        top_k,
        top_p,
        presence_penalty,
        frequency_penalty,
        max_tokens,
        timeout,
        images,
        image_max_side,
        image_max_kb,
        image_quality,
    ) -> comfy_io.NodeOutput:
        api_key = config.get_api_key(api_key_name)

        image_tensors = [t for t in (images or {}).values() if t is not None]
        text_part = (prompt or "").strip()

        if not image_tensors and not text_part:
            raise ValueError(
                "ArkSD LLM: connect at least one image or provide a prompt. "
                "Both were empty, so there is nothing to send."
            )
        if image_tensors and not text_part:
            text_part = FALLBACK_PROMPT

        if image_tensors:
            user_content = [{"type": "text", "text": text_part}]
            for index, tensor in enumerate(image_tensors, start=1):
                uri = encode_image_with_limit(
                    tensor, image_max_side, image_max_kb, image_quality
                )
                LOGGER.info("[ArkSD] LLM image %d encoded (%d KB base64)", index, len(uri) // 1024)
                user_content.append({"type": "image_url", "image_url": {"url": uri}})
        else:
            user_content = text_part

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            "temperature": temperature,
            "top_p": top_p,
            "presence_penalty": presence_penalty,
            "frequency_penalty": frequency_penalty,
            "max_tokens": max_tokens,
            "stream": False,
        }
        if top_k > 0:
            payload["top_k"] = top_k

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }

        client_timeout = aiohttp.ClientTimeout(total=timeout)
        async with aiohttp.ClientSession(timeout=client_timeout) as session:
            async with session.post(ARK_CHAT_URL, headers=headers, json=payload) as response:
                body = await response.text()
                if response.status != 200:
                    raise RuntimeError(
                        f"ArkSD LLM: request failed with HTTP {response.status}\n{body[:2000]}"
                    )

        try:
            text = json.loads(body)["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise RuntimeError(f"ArkSD LLM: could not parse the response: {exc}\n{body[:2000]}")

        LOGGER.info("[ArkSD] LLM returned %d characters", len(text or ""))
        return comfy_io.NodeOutput(text)


class ArkSDTexts(comfy_io.ComfyNode):
    @classmethod
    def define_schema(cls):
        autogrow = comfy_io.Autogrow.TemplateNames(
            input=comfy_io.String.Input("text", multiline=True),
            names=[f"text_{i}" for i in range(1, MAX_TEXTS + 1)],
            min=1,
        )
        return comfy_io.Schema(
            node_id="ArkSD_Texts",
            display_name="ArkSD Texts",
            category="api node/ArkSD",
            description=(
                f"Concatenate up to {MAX_TEXTS} text inputs into one string. "
                "Connecting a slot adds a fresh empty one until the cap is reached."
            ),
            inputs=[
                comfy_io.Autogrow.Input("texts", template=autogrow),
                comfy_io.String.Input(
                    "delimiter",
                    default="",
                    tooltip="Inserted between adjacent texts.",
                ),
            ],
            outputs=[comfy_io.String.Output("text")],
        )

    @classmethod
    def execute(cls, texts=None, delimiter="") -> comfy_io.NodeOutput:
        parts = [t for t in (texts or {}).values() if t is not None]
        return comfy_io.NodeOutput(delimiter.join(parts))
