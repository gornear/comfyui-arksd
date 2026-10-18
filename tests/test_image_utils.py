import base64
import io
import torch
from PIL import Image
from nodes import image_utils


def _decode(data_url: str) -> Image.Image:
    assert data_url.startswith("data:image/")
    b64 = data_url.split(",", 1)[1]
    return Image.open(io.BytesIO(base64.b64decode(b64)))


def test_small_image_passes_through_as_png():
    t = torch.rand(1, 512, 512, 3)
    out = image_utils.normalize_image(t, "reference_image_0")
    assert out.startswith("data:image/png;base64,")
    assert _decode(out).size == (512, 512)


def test_oversized_edge_is_scaled_down():
    t = torch.rand(1, 8000, 1000, 3)
    out = image_utils.normalize_image(t, "reference_image_0")
    img = _decode(out)
    assert max(img.size) <= 6000
    assert min(img.size) >= 300


def test_extreme_aspect_ratio_is_scaled():
    t = torch.rand(1, 200, 4000, 3)
    out = image_utils.normalize_image(t, "reference_image_0")
    img = _decode(out)
    ratio = img.size[0] / img.size[1]
    assert 0.4 <= ratio <= 2.5


def test_tiny_image_is_scaled_up():
    t = torch.rand(1, 100, 100, 3)
    out = image_utils.normalize_image(t, "reference_image_0")
    img = _decode(out)
    assert min(img.size) >= 300
