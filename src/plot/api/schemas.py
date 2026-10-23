"""Request and response bodies (SPEC §8.3)."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class RequestBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


# --- domains -------------------------------------------------------------------


class DomainCreate(RequestBody):
    name: str
    owner: str
    years: int | None = None
    nameservers: list[str] = []


class RenewRequest(RequestBody):
    years: int


class NameserversRequest(RequestBody):
    nameservers: list[str]


class StatusRequest(RequestBody):
    add: list[str] = []
    remove: list[str] = []


class OverridesRequest(RequestBody):
    """A field left out is unchanged; ``null`` clears the override."""

    propagation_delay: int | None = None
    ns_ttl: int | None = None


class Overrides(BaseModel):
    propagation_delay: int | None
    ns_ttl: int | None


class Pending(BaseModel):
    apply_at: datetime


class DnsVisible(BaseModel):
    published_at: datetime | None
    nameservers: list[str]
    pending: list[Pending]


class Domain(BaseModel):
    name: str
    owner: str
    status: list[str]
    expired: bool
    created_at: datetime
    expires_at: datetime
    nameservers: list[str]
    overrides: Overrides
    dns_visible: DnsVisible


class DomainList(BaseModel):
    items: list[Domain]
    next_cursor: str | None


class DomainCheck(BaseModel):
    name: str
    available: bool
    reason: str | None = None


# --- hosts ---------------------------------------------------------------------


class HostCreate(RequestBody):
    name: str
    ipv4: list[str] = []
    ipv6: list[str] = []


class HostUpdate(RequestBody):
    ipv4: list[str] | None = None
    ipv6: list[str] | None = None


class Host(BaseModel):
    name: str
    kind: str
    parent_domain: str | None
    ipv4: list[str]
    ipv6: list[str]
    used_by: list[str]


class HostList(BaseModel):
    items: list[Host]


# --- history -------------------------------------------------------------------


class Event(BaseModel):
    ts: datetime
    action: str
    actor: str
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    request_id: str


class EventList(BaseModel):
    items: list[Event]


# --- admin ---------------------------------------------------------------------


class Settings(BaseModel):
    propagation_delay: int
    ns_ttl: int
    default_years: int
    expiry_grace_days: int
    flush_on_apply: bool


class SettingsUpdate(RequestBody):
    """Fields left out keep their current value."""

    propagation_delay: int | None = None
    ns_ttl: int | None = None
    default_years: int | None = None
    expiry_grace_days: int | None = None
    flush_on_apply: bool | None = None


class ResetRequest(RequestBody):
    prefix: str | None = None
    all: bool = False


class ResetResult(BaseModel):
    deleted_domains: list[str]
    deleted_hosts: list[str]


class FlushRequest(RequestBody):
    domain: str | None = None


class FlushResult(BaseModel):
    flushed: str | None


class ReconcileResult(BaseModel):
    fixed: list[str]
