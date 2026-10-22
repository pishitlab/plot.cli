from ipaddress import IPv4Address, IPv4Network
from pathlib import Path

import pytest
from pydantic import ValidationError

from plot.core.settings import RuntimeSettings, load_env_config, load_runtime_defaults

CONFIG = Path(__file__).resolve().parents[2] / "config"


def test_runtime_defaults_file_matches_spec() -> None:
    assert load_runtime_defaults(CONFIG / "settings.default.yml") == RuntimeSettings(
        propagation_delay=0,
        ns_ttl=300,
        default_years=1,
        expiry_grace_days=30,
        flush_on_apply=True,
    )


@pytest.mark.parametrize(
    "bad",
    [
        {"propagation_delay": -1},
        {"ns_ttl": -1},
        {"default_years": 0},
        {"default_years": 11},
        {"expiry_grace_days": -1},
        {"ns_ttl": "300"},
        {"unknown": 1},
    ],
)
def test_runtime_settings_validation(bad: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        RuntimeSettings.model_validate(bad)


def test_env_config_reads_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)  # no stray .env
    monkeypatch.setenv("API_KEY", "k1")
    monkeypatch.setenv("PDNS_API_KEY", "k2")
    monkeypatch.setenv("SUBNET", "10.9.0.0/24")
    config = load_env_config()
    assert config.api_key.get_secret_value() == "k1"
    assert config.subnet == IPv4Network("10.9.0.0/24")
    assert config.pdns_root_ip == IPv4Address("172.28.0.10")
    assert config.bind_addr == "127.0.0.1"
    assert "k1" not in repr(config)


def test_env_config_requires_api_keys(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("API_KEY", raising=False)
    monkeypatch.delenv("PDNS_API_KEY", raising=False)
    with pytest.raises(ValidationError):
        load_env_config()
