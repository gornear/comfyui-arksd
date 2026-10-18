"""Async client for the Ark video generation API.

This talks to the generation plane directly over httpx instead of using the
``arkruntime`` SDK. The SDK does not cover the asset management API, which has
to be hand-written anyway, and it lags behind new request parameters such as
``omni_reference_task_type`` and ``draft``.

Auth is an API key sent as ``Authorization: Bearer <key>``.
"""

import asyncio
import logging

import httpx

from .constants import DEFAULT_POLL_INTERVAL, DEFAULT_TIMEOUT

LOGGER = logging.getLogger("arksd")

BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
TASKS_PATH = "/contents/generations/tasks"

# Per-request timeout. The read timeout only covers a single HTTP round trip;
# the overall wait for a video is bounded by the node's `timeout` parameter.
REQUEST_TIMEOUT = httpx.Timeout(connect=10.0, read=60.0, write=60.0, pool=10.0)

# Task states that mean the task will not change again.
TERMINAL_STATUSES = {"succeeded", "failed", "cancelled", "expired"}

# Error codes that usually mean the model was never opened on this account.
_MODEL_HINTS = {"ModelNotOpen", "AccessDenied", "InvalidParameter"}


class ArkError(Exception):
    """An error returned by the Ark API, or a failure while talking to it."""

    def __init__(self, code: str, message: str, status: int | None = None, hint: str = ""):
        self.code = code
        self.message = message
        self.status = status
        self.hint = hint
        text = f"[ArkSD] Ark API error {code}: {message}"
        if hint:
            text += f"\nHint: {hint}"
        super().__init__(text)

    @classmethod
    def from_response(cls, status: int, payload: dict) -> "ArkError":
        error = payload.get("error") if isinstance(payload, dict) else None
        if isinstance(error, dict):
            code = str(error.get("code") or f"HTTP{status}")
            message = str(error.get("message") or payload)
        else:
            code = f"HTTP{status}"
            message = str(payload)
        hint = ""
        if code in _MODEL_HINTS:
            hint = (
                "The model may not be opened on this account. Open it in the Ark "
                "console (Model Square -> the Seedance model -> Open), then retry."
            )
        return cls(code, message, status, hint)


def build_content(prompt: str, images: list, videos: list, audios: list) -> list[dict]:
    """Build the ``content`` array for a create-task request.

    The text item is omitted when the prompt is empty, which is valid for
    image-only and asset-only requests.
    """
    content: list[dict] = []
    if prompt:
        content.append({"type": "text", "text": prompt})
    for url in images:
        content.append({"type": "image_url", "image_url": {"url": url}, "role": "reference_image"})
    for url in videos:
        content.append({"type": "video_url", "video_url": {"url": url}, "role": "reference_video"})
    for url in audios:
        content.append({"type": "audio_url", "audio_url": {"url": url}, "role": "reference_audio"})
    return content


def _headers(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}


async def _request(method: str, path: str, api_key: str, **kwargs) -> dict:
    url = f"{BASE_URL}{path}"
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as http:
        try:
            response = await http.request(method, url, headers=_headers(api_key), **kwargs)
        except httpx.HTTPError as exc:
            raise ArkError("NetworkError", f"{method} {url} failed: {exc}") from exc
    if response.status_code >= 400:
        try:
            payload = response.json()
        except ValueError:
            payload = {"error": {"code": f"HTTP{response.status_code}", "message": response.text}}
        raise ArkError.from_response(response.status_code, payload)
    if not response.content:
        return {}
    return response.json()


async def list_models(api_key: str) -> list[dict]:
    """Return the Ark model catalog, minus retired models.

    This is the platform-wide catalog, not the set of models this account has
    opened; Ark exposes no endpoint for the latter. A model that appears here
    can still answer ``ModelNotOpen`` when submitted, which the caller reports
    with a console hint.
    """
    payload = await _request("GET", "/models", api_key)
    models = []
    for entry in payload.get("data") or []:
        if entry.get("status") == "Shutdown":
            continue
        model_id = str(entry.get("id") or "")
        if not model_id:
            continue
        models.append(
            {
                "id": model_id,
                "name": str(entry.get("name") or model_id),
                "status": str(entry.get("status") or ""),
                "domain": str(entry.get("domain") or ""),
            }
        )
    models.sort(key=lambda m: (m["domain"], m["id"]))
    LOGGER.info("[ArkSD] listed %d models", len(models))
    return models


async def create_task(api_key: str, body: dict) -> str:
    """Create a generation task and return its id."""
    payload = await _request("POST", TASKS_PATH, api_key, json=body)
    task_id = payload.get("id")
    if not task_id:
        raise ArkError("MissingTaskId", f"Create task response had no id: {payload}")
    LOGGER.info("[ArkSD] created task %s (model=%s)", task_id, body.get("model"))
    return str(task_id)


async def get_task(api_key: str, task_id: str) -> dict:
    """Return the current state of one task."""
    return await _request("GET", f"{TASKS_PATH}/{task_id}", api_key)


async def list_tasks(
    api_key: str,
    status: str | None = None,
    page_num: int = 1,
    page_size: int = 20,
) -> dict:
    """Return a page of recent tasks (the API only keeps the last 7 days)."""
    params: dict[str, object] = {"page_num": page_num, "page_size": page_size}
    if status and status != "all":
        params["filter.status"] = status
    return await _request("GET", TASKS_PATH, api_key, params=params)


async def cancel_task(api_key: str, task_id: str) -> None:
    """Cancel a task. Ark only allows this while the task is still queued."""
    await _request("DELETE", f"{TASKS_PATH}/{task_id}", api_key)
    LOGGER.info("[ArkSD] cancelled task %s", task_id)


async def wait_for_task(
    api_key: str,
    task_id: str,
    timeout: float = DEFAULT_TIMEOUT,
    poll_interval: float = DEFAULT_POLL_INTERVAL,
) -> dict:
    """Poll a task until it reaches a terminal state.

    Raises ``ArkError`` on failure, expiry, or timeout. If ComfyUI's Cancel
    button is pressed while waiting, the remote task is cancelled and the
    interrupt is re-raised so ComfyUI can unwind normally.
    """
    import comfy.model_management as model_management

    elapsed = 0.0
    while True:
        model_management.throw_exception_if_processing_interrupted()
        task = await get_task(api_key, task_id)
        status = task.get("status")
        if status == "succeeded":
            return task
        if status in TERMINAL_STATUSES:
            error = task.get("error") or {}
            raise ArkError(
                str(error.get("code") or status),
                str(error.get("message") or f"Task {task_id} ended with status {status}"),
            )
        if elapsed >= timeout:
            raise ArkError(
                "Timeout",
                f"Task {task_id} did not finish within {int(timeout)}s "
                f"(last status: {status}). The task may still be running; "
                f"query it later with ArkSD Query Task.",
            )
        LOGGER.info(
            "[ArkSD] task %s status=%s elapsed=%ds/%ds",
            task_id,
            status,
            int(elapsed),
            int(timeout),
        )
        try:
            await asyncio.sleep(poll_interval)
        except asyncio.CancelledError:
            await _cancel_quietly(api_key, task_id)
            raise
        elapsed += poll_interval


async def _cancel_quietly(api_key: str, task_id: str) -> None:
    try:
        await cancel_task(api_key, task_id)
    except Exception as exc:  # noqa: BLE001 - best effort during interrupt
        LOGGER.warning("[ArkSD] could not cancel task %s: %s", task_id, exc)


async def download_video(url: str) -> bytes:
    """Download a generated video into memory."""
    async with httpx.AsyncClient(timeout=httpx.Timeout(connect=10.0, read=300.0, write=60.0, pool=10.0)) as http:
        try:
            response = await http.get(url)
        except httpx.HTTPError as exc:
            raise ArkError("DownloadError", f"Could not download {url}: {exc}") from exc
    if response.status_code >= 400:
        raise ArkError("DownloadError", f"Download {url} returned HTTP {response.status_code}")
    return response.content
