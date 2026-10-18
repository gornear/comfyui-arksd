"""Credential loading for ArkSD.

Credentials live in two JSON files next to the package root:

* ``api_keys.json`` - Ark API keys used for the generation API (Bearer auth).
* ``ak_sk.json``    - Ark Access Key / Secret Key pairs used for the asset
  management API (HMAC-SHA256 signing). An API key does not work there.

Both files are git-ignored. Nodes only ever expose the ``customName`` of an
entry, never the secret itself, because widget values are stored in the
workflow JSON.
"""

import json
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
API_KEYS_PATH = PACKAGE_ROOT / "api_keys.json"
AK_SK_PATH = PACKAGE_ROOT / "ak_sk.json"


class ConfigError(Exception):
    """Raised when a credential file is missing, malformed, or incomplete."""


def _load_list(path: Path, label: str) -> list[dict]:
    if not path.exists():
        raise ConfigError(
            f"Credential file '{path.name}' was not found at {path}. "
            f"Copy '{label}.example' to '{label}' and fill in your credentials."
        )
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Credential file '{path.name}' is not valid JSON: {exc}") from exc
    if not isinstance(raw, list):
        raise ConfigError(
            f"Credential file '{path.name}' must contain a JSON array of entries."
        )
    for index, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise ConfigError(
                f"Credential file '{path.name}' entry {index} must be a JSON object."
            )
    return raw


def load_api_keys() -> list[dict]:
    """Return every entry of ``api_keys.json``."""
    return _load_list(API_KEYS_PATH, "api_keys.json")


def load_ak_sk() -> list[dict]:
    """Return every entry of ``ak_sk.json``."""
    return _load_list(AK_SK_PATH, "ak_sk.json")


def _names(entries: list[dict]) -> list[str]:
    return [str(entry.get("customName", "")) for entry in entries if entry.get("customName")]


def list_api_key_names() -> list[str]:
    """Return the available API key names, or an empty list when unconfigured.

    Node registration calls this at import time, so a missing file must not
    raise here.
    """
    try:
        return _names(load_api_keys())
    except ConfigError:
        return []


def list_ak_sk_names() -> list[str]:
    """Return the available AK/SK names, or an empty list when unconfigured."""
    try:
        return _names(load_ak_sk())
    except ConfigError:
        return []


def get_api_key(custom_name: str) -> str:
    """Return the API key stored under ``custom_name``."""
    entries = load_api_keys()
    for entry in entries:
        if entry.get("customName") == custom_name:
            key = entry.get("apiKey")
            if not key:
                raise ConfigError(
                    f"Entry '{custom_name}' in 'api_keys.json' has no 'apiKey' value."
                )
            return str(key)
    available = ", ".join(_names(entries)) or "<none>"
    raise ConfigError(
        f"API key '{custom_name}' was not found in 'api_keys.json'. "
        f"Available names: {available}."
    )


def get_ak_sk(custom_name: str) -> dict:
    """Return the AK/SK entry stored under ``custom_name``."""
    entries = load_ak_sk()
    for entry in entries:
        if entry.get("customName") == custom_name:
            missing = [f for f in ("accessKey", "secretKey") if not entry.get(f)]
            if missing:
                raise ConfigError(
                    f"Entry '{custom_name}' in 'ak_sk.json' is missing: {', '.join(missing)}."
                )
            return {
                "accessKey": str(entry["accessKey"]),
                "secretKey": str(entry["secretKey"]),
                "region": str(entry.get("region") or "cn-beijing"),
            }
    available = ", ".join(_names(entries)) or "<none>"
    raise ConfigError(
        f"AK/SK entry '{custom_name}' was not found in 'ak_sk.json'. "
        f"Available names: {available}."
    )
