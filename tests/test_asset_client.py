from datetime import datetime, timezone
from nodes import asset_client


def test_sign_request_headers():
    now = datetime(2026, 10, 18, 1, 0, 0, tzinfo=timezone.utc)
    headers = asset_client.sign_request(
        "AKLTtest", "secret", "cn-beijing", "ListAssets", {"Filter": {"GroupType": "AIGC"}}, now
    )
    assert headers["X-Date"] == "20261018T010000Z"
    assert headers["X-Content-Sha256"]
    assert headers["Authorization"].startswith("HMAC-SHA256 Credential=AKLTtest/20261018/cn-beijing/ark/request")
    assert "SignedHeaders=content-type;host;x-content-sha256;x-date" in headers["Authorization"]
    assert "Signature=" in headers["Authorization"]


def test_sign_request_is_deterministic():
    now = datetime(2026, 10, 18, 1, 0, 0, tzinfo=timezone.utc)
    a = asset_client.sign_request("AK", "SK", "cn-beijing", "ListAssets", {"A": 1}, now)
    b = asset_client.sign_request("AK", "SK", "cn-beijing", "ListAssets", {"A": 1}, now)
    assert a["Authorization"] == b["Authorization"]


def test_sign_request_changes_with_body():
    now = datetime(2026, 10, 18, 1, 0, 0, tzinfo=timezone.utc)
    a = asset_client.sign_request("AK", "SK", "cn-beijing", "ListAssets", {"A": 1}, now)
    b = asset_client.sign_request("AK", "SK", "cn-beijing", "ListAssets", {"A": 2}, now)
    assert a["Authorization"] != b["Authorization"]
