"""Client for the Ark asset management API.

The asset library lives on the management plane, not the generation plane:

* endpoint: ``https://ark.cn-beijing.volcengineapi.com``
* auth: Access Key / Secret Key with a Volcengine Signature V4 HMAC-SHA256
  signature. An API key does not work here.

Only read operations are implemented. Creating, updating, and deleting assets
is out of scope; users manage their library in the Ark console.
"""

import hashlib
import hmac
import json
import logging
from datetime import datetime, timezone

import httpx

from .client import ArkError

LOGGER = logging.getLogger("arksd")

HOST = "ark.cn-beijing.volcengineapi.com"
SERVICE = "ark"
VERSION = "2024-01-01"
API_BASE = f"https://{HOST}"

REQUEST_TIMEOUT = httpx.Timeout(connect=10.0, read=60.0, write=60.0, pool=10.0)

# The API requires a group type filter and accepts only one value per
# request. AIGC covers virtual avatars; LivenessFace covers real-person
# material, including assets another account authorized to this one.
GROUP_TYPES = ["AIGC", "LivenessFace"]


def _group_types_to_query(group_type: str | None) -> list[str]:
    """Expand the node's group_type selection into the types to query.

    ``All`` becomes one request per type, because the API only accepts a single
    GroupType per call and authorized real-person assets live under
    ``LivenessFace``.
    """
    if group_type in GROUP_TYPES:
        return [group_type]
    return list(GROUP_TYPES)


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _hmac(key: bytes, message: str) -> bytes:
    return hmac.new(key, message.encode("utf-8"), hashlib.sha256).digest()


def sign_request(
    access_key: str,
    secret_key: str,
    region: str,
    action: str,
    body: dict,
    now: datetime,
) -> dict[str, str]:
    """Return the signed headers for one management API call.

    Implements the Volcengine Signature V4 scheme: a canonical request is
    hashed, then a signing key is derived from the secret key through the
    standard date/region/service/request HMAC chain.
    """
    body_bytes = json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    payload_hash = _sha256_hex(body_bytes)
    x_date = now.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    short_date = x_date[:8]

    canonical_headers = (
        "content-type:application/json\n"
        f"host:{HOST}\n"
        f"x-content-sha256:{payload_hash}\n"
        f"x-date:{x_date}\n"
    )
    signed_headers = "content-type;host;x-content-sha256;x-date"
    canonical_query = f"Action={action}&Version={VERSION}"
    canonical_request = "\n".join(
        ["POST", "/", canonical_query, canonical_headers, signed_headers, payload_hash]
    )

    credential_scope = f"{short_date}/{region}/{SERVICE}/request"
    string_to_sign = "\n".join(
        [
            "HMAC-SHA256",
            x_date,
            credential_scope,
            _sha256_hex(canonical_request.encode("utf-8")),
        ]
    )

    k_date = _hmac(secret_key.encode("utf-8"), short_date)
    k_region = _hmac(k_date, region)
    k_service = _hmac(k_region, SERVICE)
    k_signing = _hmac(k_service, "request")
    signature = hmac.new(k_signing, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

    return {
        "Content-Type": "application/json",
        "X-Date": x_date,
        "X-Content-Sha256": payload_hash,
        "Authorization": (
            f"HMAC-SHA256 Credential={access_key}/{credential_scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        ),
    }


async def _call(creds: dict, action: str, body: dict) -> dict:
    now = datetime.now(timezone.utc)
    headers = sign_request(
        creds["accessKey"], creds["secretKey"], creds.get("region", "cn-beijing"), action, body, now
    )
    url = f"{API_BASE}/?Action={action}&Version={VERSION}"
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as http:
        try:
            response = await http.post(url, headers=headers, json=body)
        except httpx.HTTPError as exc:
            raise ArkError("NetworkError", f"{action} failed: {exc}") from exc
    if response.status_code >= 400:
        try:
            payload = response.json()
        except ValueError:
            payload = {"error": {"code": f"HTTP{response.status_code}", "message": response.text}}
        error = payload.get("ResponseMetadata", {}).get("Error") or payload.get("error") or {}
        raise ArkError(
            str(error.get("Code") or error.get("code") or f"HTTP{response.status_code}"),
            str(error.get("Message") or error.get("message") or response.text),
            response.status_code,
        )
    return response.json().get("Result", {})


async def _paginate(creds: dict, action: str, body: dict) -> list[dict]:
    """Follow NextToken until the result set is exhausted."""
    items: list[dict] = []
    token = None
    while True:
        page_body = dict(body)
        if token:
            page_body["NextToken"] = token
        result = await _call(creds, action, page_body)
        items.extend(result.get("Items") or [])
        token = result.get("NextToken")
        if not token:
            return items


def _project(project_name: str | None) -> str:
    """Return the project to query.

    Assets live inside an Ark project. The API silently returns an empty list
    for a project you do not own, so an unset value has to mean the default
    project rather than "search everywhere".
    """
    return (project_name or "").strip() or "default"


async def list_assets(
    creds: dict,
    group_type: str | None = None,
    group_id: str | None = None,
    asset_type: str | None = None,
    project_name: str | None = None,
) -> list[dict]:
    """Return the account's assets, optionally filtered.

    ``group_type`` is required by the API and accepts one value per request,
    so ``All`` (and an unset value) issues one query per group type and merges
    the results. The API's ``Filter`` only accepts ``GroupType``, ``GroupIds``,
    ``Name``, and ``Statuses``, so the asset type filter is applied here.
    """
    project = _project(project_name)
    items: list[dict] = []
    for current_type in _group_types_to_query(group_type):
        filter_body: dict = {"GroupType": current_type}
        if group_id:
            filter_body["GroupIds"] = [group_id]
        body = {
            "Filter": filter_body,
            "MaxResults": 100,
            "SortBy": "CreateTime",
            "SortOrder": "Desc",
            "ProjectName": project,
        }
        items.extend(await _paginate(creds, "ListAssets", body))
    if asset_type and asset_type != "All":
        items = [item for item in items if item.get("AssetType") == asset_type]
    LOGGER.info("[ArkSD] listed %d assets in project %r", len(items), project)
    return items


async def list_asset_groups(
    creds: dict,
    group_type: str | None = None,
    project_name: str | None = None,
) -> list[dict]:
    """Return the account's asset groups, merging every type when ``All``."""
    project = _project(project_name)
    items: list[dict] = []
    for current_type in _group_types_to_query(group_type):
        body = {
            "Filter": {"GroupType": current_type},
            "MaxResults": 100,
            "SortBy": "CreateTime",
            "SortOrder": "Desc",
            "ProjectName": project,
        }
        items.extend(await _paginate(creds, "ListAssetGroups", body))
    LOGGER.info("[ArkSD] listed %d asset groups in project %r", len(items), project)
    return items
