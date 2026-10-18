"""ArkSD LLM and ArkSD Texts nodes.

The LLM node is the reference customLLM node with its own api_key/api_url
widgets removed: it targets the Ark chat completions endpoint and reads its
credential from api_keys.json through the standard api_key_name combo.
"""

import asyncio
import base64
import json
from unittest.mock import AsyncMock, patch

import pytest
import torch

from nodes import config, nodes_llm


def _schema_ids(node_cls):
    return [i.id for i in node_cls.define_schema().inputs]


# ---------------------------------------------------------------- schema


def test_llm_node_id_and_category():
    schema = nodes_llm.ArkSDLLM.define_schema()
    assert schema.node_id == "ArkSD_LLM"
    assert schema.category == "api node/ArkSD"


def test_llm_has_no_api_url_or_api_key_widgets():
    ids = _schema_ids(nodes_llm.ArkSDLLM)
    assert "api_key_name" in ids
    assert "api_url" not in ids
    assert "api_key" not in ids


def test_llm_keeps_sampling_widgets():
    ids = _schema_ids(nodes_llm.ArkSDLLM)
    for name in (
        "model",
        "system_prompt",
        "prompt",
        "temperature",
        "top_k",
        "top_p",
        "presence_penalty",
        "frequency_penalty",
        "max_tokens",
        "timeout",
        "images",
        "image_max_side",
        "image_max_kb",
        "image_quality",
    ):
        assert name in ids, name


def test_texts_node_id_and_category():
    schema = nodes_llm.ArkSDTexts.define_schema()
    assert schema.node_id == "ArkSD_Texts"
    assert schema.category == "api node/ArkSD"


def test_texts_joins_with_delimiter():
    result = nodes_llm.ArkSDTexts.execute(texts={"text_1": "a", "text_2": "b"}, delimiter=",")
    assert result.args[0] == "a,b"


def test_texts_skips_none_and_empty():
    result = nodes_llm.ArkSDTexts.execute(texts={"text_1": "a", "text_2": None}, delimiter="-")
    assert result.args[0] == "a"


def test_texts_handles_missing_input():
    assert nodes_llm.ArkSDTexts.execute(texts=None).args[0] == ""


# ---------------------------------------------------------------- request


def _run_llm(**overrides):
    kwargs = {
        "api_key_name": "A",
        "model": "doubao-seed-2-0",
        "system_prompt": "sys",
        "prompt": "hello",
        "temperature": 0.0,
        "top_k": 0,
        "top_p": 0.3,
        "presence_penalty": 0.0,
        "frequency_penalty": 0.0,
        "max_tokens": 128,
        "timeout": 30,
        "images": None,
        "image_max_side": 1024,
        "image_max_kb": 1024,
        "image_quality": 95,
    }
    kwargs.update(overrides)
    return asyncio.run(nodes_llm.ArkSDLLM.execute(**kwargs))


def _fake_post(captured, reply_text="answer"):
    response_payload = {"choices": [{"message": {"content": reply_text}}]}

    class FakeResponse:
        status = 200

        async def text(self):
            return json.dumps(response_payload)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

    class FakeSession:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        def post(self, url, headers=None, json=None):
            captured["url"] = url
            captured["headers"] = headers
            captured["payload"] = json
            return FakeResponse()

    return FakeSession


def test_llm_posts_to_ark_endpoint_with_bearer_key():
    captured = {}
    with patch.object(config, "get_api_key", return_value="secret-key"), patch.object(
        nodes_llm.aiohttp, "ClientSession", _fake_post(captured)
    ):
        result = _run_llm()

    assert result.args[0] == "answer"
    assert captured["url"] == nodes_llm.ARK_CHAT_URL
    assert captured["headers"]["Authorization"] == "Bearer secret-key"
    assert captured["payload"]["model"] == "doubao-seed-2-0"
    assert captured["payload"]["messages"][0]["content"] == "sys"
    assert captured["payload"]["messages"][1]["content"] == "hello"
    assert captured["payload"]["stream"] is False
    assert "top_k" not in captured["payload"]


def test_llm_sends_top_k_when_positive():
    captured = {}
    with patch.object(config, "get_api_key", return_value="k"), patch.object(
        nodes_llm.aiohttp, "ClientSession", _fake_post(captured)
    ):
        _run_llm(top_k=5)
    assert captured["payload"]["top_k"] == 5


def test_llm_rejects_empty_prompt_without_images():
    with patch.object(config, "get_api_key", return_value="k"):
        with pytest.raises(ValueError):
            _run_llm(prompt="   ")


def test_llm_image_only_uses_fallback_prompt():
    captured = {}
    image = torch.rand(1, 32, 32, 3)
    with patch.object(config, "get_api_key", return_value="k"), patch.object(
        nodes_llm.aiohttp, "ClientSession", _fake_post(captured)
    ):
        _run_llm(prompt="", images={"image_1": image})

    content = captured["payload"]["messages"][1]["content"]
    assert isinstance(content, list)
    assert content[0]["text"] == nodes_llm.FALLBACK_PROMPT
    assert content[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")


def test_llm_missing_key_raises():
    with patch.object(config, "get_api_key", side_effect=config.ConfigError("no key")):
        with pytest.raises(config.ConfigError):
            _run_llm()


def test_image_encoder_keeps_payload_under_limit():
    """A large image must be shrunk to satisfy the size cap, not rejected."""
    tensor = torch.rand(1, 900, 900, 3)
    uri = nodes_llm.encode_image_with_limit(tensor, max_side=256, max_kb=64, quality=95)
    payload = uri.split(",", 1)[1]
    assert len(base64.b64decode(payload)) <= 64 * 1024 + 4096
    assert uri.startswith("data:image/jpeg;base64,")
