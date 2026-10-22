"""Process configuration (.env, SPEC §13.1) and runtime settings (SPEC §13.4)."""

from ipaddress import IPv4Address, IPv4Network
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, IPvAnyAddress, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

MAX_TTL = 2_147_483_647


class EnvConfig(BaseSettings):
    """Deployment configuration read from the environment and ``.env``."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", frozen=True)

    bind_addr: str = "127.0.0.1"
    api_key: SecretStr
    subnet: IPv4Network = IPv4Network("172.28.0.0/24")
    pdns_root_ip: IPv4Address = IPv4Address("172.28.0.10")
    pdns_api_key: SecretStr
    upstream_dns: IPvAnyAddress = IPv4Address("1.1.1.1")
    cache_max_ttl: int = Field(default=3600, ge=0, le=MAX_TTL)
    data_dir: Path = Path("./data")


class RuntimeSettings(BaseModel):
    """Settings an operator can change at runtime (persisted in the ``settings`` table)."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    propagation_delay: int = Field(default=0, ge=0)
    ns_ttl: int = Field(default=300, ge=0, le=MAX_TTL)
    default_years: int = Field(default=1, ge=1, le=10)
    expiry_grace_days: int = Field(default=30, ge=0)
    flush_on_apply: bool = True


def load_env_config() -> EnvConfig:
    # Required fields come from the environment, which mypy cannot see.
    return EnvConfig()  # type: ignore[call-arg]


def load_runtime_defaults(path: Path) -> RuntimeSettings:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return RuntimeSettings.model_validate(data)
