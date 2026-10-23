from datetime import timedelta

from sqlalchemy.orm import Session

from plot.db.models import PendingChange
from plot.dns.projector import Snapshot
from plot.dns.scheduler import (
    Backoff,
    apply_due,
    due_changes,
    propagation_delay,
    published_snapshot,
    schedule_change,
)
from plot.services.context import ServiceContext
from plot.services.domains import DomainService
from tests.conftest import T0

A = {"nameservers": ["ns1.a.net", "ns2.a.net"], "ttl": 300, "glue": {}}
B = {"nameservers": ["ns1.b.net", "ns2.b.net"], "ttl": 300, "glue": {}}


class RecordingApplier:
    def __init__(self, fail_on: set[str] | None = None) -> None:
        self.calls: list[tuple[str, Snapshot, Snapshot]] = []
        self.fail_on = fail_on or set()

    def __call__(self, name: str, old: Snapshot, new: Snapshot) -> None:
        if name in self.fail_on:
            raise ConnectionError("pdns down")
        self.calls.append((name, old, new))


def test_R_PUB_05_apply_at_is_now_plus_delay(session: Session) -> None:
    change = schedule_change(session, "shop.com", A, T0, 20)
    assert (change.scheduled_at, change.apply_at) == (T0, T0 + timedelta(seconds=20))
    assert due_changes(session, T0 + timedelta(seconds=19)) == []
    assert due_changes(session, T0 + timedelta(seconds=20)) == [change]


def test_R_PUB_05_delay_from_override_or_setting(ctx: ServiceContext) -> None:
    domains = DomainService(ctx)
    domains.register("shop.com", owner="a")
    settings = ctx.settings.model_copy(update={"propagation_delay": 15})
    assert propagation_delay(ctx.session, "shop.com", settings) == 15
    domains.set_overrides("shop.com", propagation_delay=0)
    assert propagation_delay(ctx.session, "shop.com", settings) == 0
    assert propagation_delay(ctx.session, "deleted.com", settings) == 15


def test_R_PUB_06_applied_in_apply_at_then_id_order(session: Session) -> None:
    schedule_change(session, "b.com", B, T0, 5)
    schedule_change(session, "a.com", A, T0, 5)
    schedule_change(session, "c.com", A, T0, 1)
    applier = RecordingApplier()
    result = apply_due(session, T0 + timedelta(seconds=10), applier)
    assert result.applied == ["c.com", "b.com", "a.com"]
    assert [c[0] for c in applier.calls] == ["c.com", "b.com", "a.com"]


def test_R_PUB_06_newer_snapshot_supersedes_older(session: Session) -> None:
    # old change with a long delay, then a newer change with no delay
    schedule_change(session, "shop.com", A, T0, 60)
    schedule_change(session, "shop.com", B, T0 + timedelta(seconds=1), 0)
    applier = RecordingApplier()
    apply_due(session, T0 + timedelta(seconds=1), applier)
    assert applier.calls == [("shop.com", None, B)]
    # the older change never overwrites the newer one when its time comes
    assert apply_due(session, T0 + timedelta(seconds=61), applier).applied == []
    assert published_snapshot(session, "shop.com") == B
    assert session.query(PendingChange).filter(PendingChange.applied_at.is_(None)).count() == 0


def test_R_PUB_06_both_due_only_latest_applied(session: Session) -> None:
    schedule_change(session, "shop.com", A, T0, 0)
    schedule_change(session, "shop.com", B, T0, 0)
    applier = RecordingApplier()
    apply_due(session, T0, applier)
    assert applier.calls == [("shop.com", None, B)]
    assert published_snapshot(session, "shop.com") == B
    assert due_changes(session, T0) == []


def test_R_PUB_06_unchanged_snapshot_is_not_reapplied(session: Session) -> None:
    schedule_change(session, "shop.com", A, T0, 0)
    applier = RecordingApplier()
    apply_due(session, T0, applier)
    schedule_change(session, "shop.com", A, T0, 0)
    assert apply_due(session, T0, applier).applied == []
    assert len(applier.calls) == 1
    schedule_change(session, "shop.com", None, T0, 0)
    assert apply_due(session, T0, applier).applied == ["shop.com"]
    assert published_snapshot(session, "shop.com") is None


def test_R_PUB_09_failure_keeps_change_pending_without_blocking_others(session: Session) -> None:
    schedule_change(session, "a.com", A, T0, 0)
    schedule_change(session, "b.com", B, T0, 0)
    failing = RecordingApplier(fail_on={"a.com"})
    result = apply_due(session, T0, failing)
    # a.com stays pending for a retry; b.com is not held hostage by it
    assert result.applied == ["b.com"] and result.failed == ["a.com"]
    assert isinstance(result.error, ConnectionError)
    assert [c.domain_name for c in due_changes(session, T0)] == ["a.com"]
    retry = apply_due(session, T0 + timedelta(seconds=1), RecordingApplier())
    assert retry.applied == ["a.com"] and retry.error is None and retry.failed == []


def test_R_PUB_09_order_within_a_failing_domain_is_kept(session: Session) -> None:
    schedule_change(session, "a.com", A, T0, 0)
    failing = RecordingApplier(fail_on={"a.com"})
    apply_due(session, T0, failing)
    schedule_change(session, "a.com", B, T0 + timedelta(seconds=1), 0)
    applier = RecordingApplier()
    apply_due(session, T0 + timedelta(seconds=1), applier)
    assert applier.calls == [("a.com", None, B)]  # the newer snapshot wins, A never lands


def test_R_PUB_09_backoff_1_2_4_capped_at_30() -> None:
    backoff = Backoff()
    assert [backoff.failed() for _ in range(8)] == [1, 2, 4, 8, 16, 30, 30, 30]
    backoff.reset()
    assert backoff.failed() == 1
