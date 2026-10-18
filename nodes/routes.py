"""HTTP routes that back the frontend extensions.

The asset picker and the task list are DOM widgets driven by JavaScript, so
they need data the node schema cannot carry. These routes serve that data.

Security notes:

* Routes never return an API key or an AK/SK. Only ``customName`` values and
  business data leave the process.
* Routes are served by ComfyUI's own aiohttp server on its normal local port.
"""

import logging
import time

from aiohttp import web

from . import asset_client, client, config
from .constants import ASSET_CACHE_TTL

LOGGER = logging.getLogger("arksd")


class TTLCache:
    """A tiny time-based cache for asset listings."""

    def __init__(self, ttl: float = ASSET_CACHE_TTL):
        self.ttl = ttl
        self._store: dict[str, tuple[float, object]] = {}

    def get(self, key: str):
        entry = self._store.get(key)
        if entry is None:
            return None
        stored_at, value = entry
        if time.monotonic() - stored_at > self.ttl:
            del self._store[key]
            return None
        return value

    def put(self, key: str, value) -> None:
        self._store[key] = (time.monotonic(), value)

    def invalidate(self, key: str) -> None:
        self._store.pop(key, None)


ASSET_CACHE = TTLCache()


def _error(message: str, status: int = 400) -> web.Response:
    return web.json_response({"error": message}, status=status)


def _int_param(source: dict, name: str, default: int) -> int:
    """Read an int from a query dict, falling back on anything unparseable."""
    try:
        return int(source.get(name, default))
    except (TypeError, ValueError):
        return default


def _asset_key(ak_sk_name: str, group_type: str, group_id: str, asset_type: str, project: str) -> str:
    return f"{ak_sk_name}|{group_type}|{group_id}|{asset_type}|{project}"


def _slim_asset(item: dict) -> dict:
    """Keep only the fields the frontend needs."""
    return {
        "id": item.get("Id", ""),
        "name": item.get("Name", ""),
        "type": item.get("AssetType", ""),
        "url": item.get("URL", ""),
        "group_id": item.get("GroupId", ""),
        "status": item.get("Status", ""),
    }


async def handle_config(request: web.Request) -> web.Response:
    return web.json_response(
        {
            "api_keys": config.list_api_key_names(),
            "ak_sk": config.list_ak_sk_names(),
        }
    )


async def handle_assets(request: web.Request) -> web.Response:
    ak_sk_name = request.query.get("ak_sk_name", "")
    group_type = request.query.get("group_type", "AIGC")
    group_id = request.query.get("group_id", "")
    asset_type = request.query.get("asset_type", "Image")
    project_name = request.query.get("project_name", "")
    refresh = request.query.get("refresh", "0") == "1"

    key = _asset_key(ak_sk_name, group_type, group_id, asset_type, project_name)
    if refresh:
        ASSET_CACHE.invalidate(key)
    cached = ASSET_CACHE.get(key)
    if cached is not None:
        return web.json_response({"items": cached})

    try:
        creds = config.get_ak_sk(ak_sk_name)
        items = await asset_client.list_assets(
            creds,
            group_type=group_type,
            group_id=group_id or None,
            asset_type=asset_type,
            project_name=project_name or None,
        )
    except (config.ConfigError, client.ArkError) as exc:
        return _error(str(exc))

    slim = [_slim_asset(item) for item in items]
    ASSET_CACHE.put(key, slim)
    return web.json_response({"items": slim})


async def handle_asset_groups(request: web.Request) -> web.Response:
    ak_sk_name = request.query.get("ak_sk_name", "")
    group_type = request.query.get("group_type", "AIGC")
    project_name = request.query.get("project_name", "")
    try:
        creds = config.get_ak_sk(ak_sk_name)
        groups = await asset_client.list_asset_groups(
            creds, group_type=group_type, project_name=project_name or None
        )
    except (config.ConfigError, client.ArkError) as exc:
        return _error(str(exc))
    return web.json_response(
        {
            "items": [
                {
                    "id": group.get("Id", ""),
                    "name": group.get("Name", ""),
                    "type": group.get("GroupType", ""),
                }
                for group in groups
            ]
        }
    )


async def handle_tasks(request: web.Request) -> web.Response:
    api_key_name = request.query.get("api_key_name", "")
    status = request.query.get("status", "all")
    page_num = _int_param(request.query, "page_num", 1)
    page_size = _int_param(request.query, "page_size", 20)
    try:
        api_key = config.get_api_key(api_key_name)
        payload = await client.list_tasks(
            api_key, status=status, page_num=page_num, page_size=page_size
        )
    except (config.ConfigError, client.ArkError) as exc:
        return _error(str(exc))
    return web.json_response(
        {"items": payload.get("items") or [], "total": payload.get("total", 0)}
    )


async def handle_cancel(request: web.Request) -> web.Response:
    task_id = request.match_info.get("task_id", "")
    api_key_name = request.query.get("api_key_name", "")
    try:
        api_key = config.get_api_key(api_key_name)
        await client.cancel_task(api_key, task_id)
    except (config.ConfigError, client.ArkError) as exc:
        return _error(str(exc))
    return web.json_response({"cancelled": True})


def register_routes() -> None:
    """Attach the routes to ComfyUI's aiohttp server."""
    from server import PromptServer

    routes = PromptServer.instance.routes  # noqa: F841 - fails fast if no server
    routes.get("/arksd/config")(handle_config)
    routes.get("/arksd/assets")(handle_assets)
    routes.get("/arksd/asset_groups")(handle_asset_groups)
    routes.get("/arksd/tasks")(handle_tasks)
    routes.post("/arksd/tasks/{task_id}/cancel")(handle_cancel)
    LOGGER.info("[ArkSD] registered HTTP routes")
