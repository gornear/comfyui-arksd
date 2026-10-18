import json
import pytest
from nodes import config


def test_load_api_keys_missing_file(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "API_KEYS_PATH", tmp_path / "nope.json")
    with pytest.raises(config.ConfigError) as exc:
        config.load_api_keys()
    assert "api_keys.json" in str(exc.value)


def test_load_api_keys_malformed(tmp_path, monkeypatch):
    p = tmp_path / "api_keys.json"
    p.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(config, "API_KEYS_PATH", p)
    with pytest.raises(config.ConfigError):
        config.load_api_keys()


def test_get_api_key_by_name(tmp_path, monkeypatch):
    p = tmp_path / "api_keys.json"
    p.write_text(json.dumps([{"customName": "A", "apiKey": "k1"}]), encoding="utf-8")
    monkeypatch.setattr(config, "API_KEYS_PATH", p)
    assert config.get_api_key("A") == "k1"
    assert config.list_api_key_names() == ["A"]


def test_get_api_key_unknown_name(tmp_path, monkeypatch):
    p = tmp_path / "api_keys.json"
    p.write_text(json.dumps([{"customName": "A", "apiKey": "k1"}]), encoding="utf-8")
    monkeypatch.setattr(config, "API_KEYS_PATH", p)
    with pytest.raises(config.ConfigError) as exc:
        config.get_api_key("B")
    assert "B" in str(exc.value)


def test_get_ak_sk(tmp_path, monkeypatch):
    p = tmp_path / "ak_sk.json"
    p.write_text(json.dumps([{"customName": "G", "accessKey": "ak", "secretKey": "sk", "region": "cn-beijing"}]), encoding="utf-8")
    monkeypatch.setattr(config, "AK_SK_PATH", p)
    creds = config.get_ak_sk("G")
    assert creds["accessKey"] == "ak"
    assert creds["region"] == "cn-beijing"
