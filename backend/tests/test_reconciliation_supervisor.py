import pytest
from backend.execution.reconciliation_supervisor import (
    ReconciliationSupervisor,
    PositionSnapshot,
    ReconciliationStatus,
)


def test_synced_positions():
    supervisor = ReconciliationSupervisor()

    timeline = PositionSnapshot(side="long", size=1.0)
    exchange = PositionSnapshot(side="long", size=1.0)

    result = supervisor.reconcile(timeline, exchange)

    assert result.status == ReconciliationStatus.SYNCED


def test_soft_desync():
    supervisor = ReconciliationSupervisor(soft_tolerance=0.05)

    timeline = PositionSnapshot(side="long", size=1.0)
    exchange = PositionSnapshot(side="long", size=0.97)

    result = supervisor.reconcile(timeline, exchange)

    assert result.status == ReconciliationStatus.SOFT_DESYNC


def test_hard_desync_size():
    supervisor = ReconciliationSupervisor(soft_tolerance=0.02)

    timeline = PositionSnapshot(side="long", size=1.0)
    exchange = PositionSnapshot(side="long", size=0.7)

    result = supervisor.reconcile(timeline, exchange)

    assert result.status == ReconciliationStatus.HARD_DESYNC


def test_hard_desync_side():
    supervisor = ReconciliationSupervisor()

    timeline = PositionSnapshot(side="long", size=1.0)
    exchange = PositionSnapshot(side="short", size=1.0)

    result = supervisor.reconcile(timeline, exchange)

    assert result.status == ReconciliationStatus.HARD_DESYNC
