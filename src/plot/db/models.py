"""SQLite schema (SPEC §5). Times are UTC ISO-8601 strings; names are lowercase, no trailing dot."""

from datetime import UTC, datetime
from typing import Any, ClassVar

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Dialect,
    ForeignKey,
    Integer,
    String,
    TypeDecorator,
    false,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

_TS_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"


class UtcDateTime(TypeDecorator[datetime]):
    """Aware UTC datetime stored as fixed-width ISO-8601 text, so SQL string order = time order."""

    impl = String(27)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> str | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetime cannot be stored; use an aware UTC datetime")
        return value.astimezone(UTC).strftime(_TS_FORMAT)

    def process_result_value(self, value: str | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        return datetime.strptime(value, _TS_FORMAT).replace(tzinfo=UTC)


class Base(DeclarativeBase):
    type_annotation_map: ClassVar[dict[Any, Any]] = {
        datetime: UtcDateTime(),
        dict[str, Any]: JSON(),
    }


class Domain(Base):
    __tablename__ = "domains"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(253), unique=True)
    suffix: Mapped[str] = mapped_column(String(253))
    label: Mapped[str] = mapped_column(String(63))
    owner: Mapped[str] = mapped_column(String(255))
    auth_code: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime]
    expires_at: Mapped[datetime]
    updated_at: Mapped[datetime]
    ns_ttl_override: Mapped[int | None]
    delay_override: Mapped[int | None]
    # Provider domains created by `plot seed provider`; kept by /admin/reset.
    seed: Mapped[bool] = mapped_column(default=False, server_default=false())

    statuses: Mapped[list["DomainStatus"]] = relationship(
        back_populates="domain", cascade="all, delete-orphan", order_by="DomainStatus.status"
    )
    nameservers: Mapped[list["DomainNs"]] = relationship(
        back_populates="domain", cascade="all, delete-orphan", order_by="DomainNs.position"
    )


class DomainStatus(Base):
    __tablename__ = "domain_statuses"
    __table_args__ = (
        CheckConstraint(
            "status IN ('clientHold', 'serverHold', 'pendingDelete')", name="ck_status_value"
        ),
    )

    domain_id: Mapped[int] = mapped_column(
        ForeignKey("domains.id", ondelete="CASCADE"), primary_key=True
    )
    status: Mapped[str] = mapped_column(String(32), primary_key=True)

    domain: Mapped[Domain] = relationship(back_populates="statuses")


class Host(Base):
    __tablename__ = "hosts"
    __table_args__ = (CheckConstraint("kind IN ('subordinate', 'external')", name="ck_host_kind"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(253), unique=True)
    kind: Mapped[str] = mapped_column(String(16))
    parent_domain_id: Mapped[int | None] = mapped_column(
        ForeignKey("domains.id", ondelete="CASCADE")
    )
    created_at: Mapped[datetime]

    parent_domain: Mapped[Domain | None] = relationship()
    addrs: Mapped[list["HostAddr"]] = relationship(
        back_populates="host", cascade="all, delete-orphan", order_by="HostAddr.address"
    )


class HostAddr(Base):
    __tablename__ = "host_addrs"
    __table_args__ = (CheckConstraint("family IN (4, 6)", name="ck_addr_family"),)

    host_id: Mapped[int] = mapped_column(
        ForeignKey("hosts.id", ondelete="CASCADE"), primary_key=True
    )
    address: Mapped[str] = mapped_column(String(45), primary_key=True)
    family: Mapped[int] = mapped_column(Integer)

    host: Mapped[Host] = relationship(back_populates="addrs")


class DomainNs(Base):
    __tablename__ = "domain_ns"

    domain_id: Mapped[int] = mapped_column(
        ForeignKey("domains.id", ondelete="CASCADE"), primary_key=True
    )
    host_id: Mapped[int] = mapped_column(ForeignKey("hosts.id"), primary_key=True)
    position: Mapped[int]

    domain: Mapped[Domain] = relationship(back_populates="nameservers")
    host: Mapped[Host] = relationship()


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime]
    request_id: Mapped[str] = mapped_column(String(64))
    actor: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64))
    domain_name: Mapped[str | None] = mapped_column(String(253), index=True)
    host_name: Mapped[str | None] = mapped_column(String(253), index=True)
    before: Mapped[dict[str, Any] | None]
    after: Mapped[dict[str, Any] | None]


class PendingChange(Base):
    __tablename__ = "pending_changes"

    id: Mapped[int] = mapped_column(primary_key=True)
    domain_name: Mapped[str] = mapped_column(String(253), index=True)
    snapshot: Mapped[dict[str, Any] | None]
    scheduled_at: Mapped[datetime]
    apply_at: Mapped[datetime]
    applied_at: Mapped[datetime | None]


class PublishedState(Base):
    __tablename__ = "published_state"

    domain_name: Mapped[str] = mapped_column(String(253), primary_key=True)
    snapshot: Mapped[dict[str, Any] | None]
    published_at: Mapped[datetime]


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON)
