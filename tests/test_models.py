"""Model catalog lookup for the ArkSD LLM model picker."""

import asyncio
from unittest.mock import patch

from nodes import client


def _payload(*models):
    return {"data": list(models)}


def test_list_models_drops_shutdown_entries():
    payload = _payload(
        {"id": "live-model", "name": "live", "status": None, "domain": "LLM"},
        {"id": "dead-model", "name": "dead", "status": "Shutdown", "domain": "LLM"},
        {"id": "retiring-model", "name": "retiring", "status": "Retiring", "domain": "LLM"},
    )
    with patch.object(client, "_request", return_value=payload):
        models = asyncio.run(client.list_models("k"))

    ids = [m["id"] for m in models]
    assert ids == ["live-model", "retiring-model"]


def test_list_models_sorts_by_domain():
    payload = _payload(
        {"id": "b", "name": "b", "status": None, "domain": "VLM"},
        {"id": "a", "name": "a", "status": None, "domain": "ImageGeneration"},
    )
    with patch.object(client, "_request", return_value=payload):
        models = asyncio.run(client.list_models("k"))

    assert [m["domain"] for m in models] == ["ImageGeneration", "VLM"]


def test_list_models_tolerates_missing_fields():
    payload = _payload({"id": "x"})
    with patch.object(client, "_request", return_value=payload):
        models = asyncio.run(client.list_models("k"))

    assert models == [{"id": "x", "name": "x", "status": "", "domain": ""}]


def test_list_models_empty_payload():
    with patch.object(client, "_request", return_value={}):
        assert asyncio.run(client.list_models("k")) == []
