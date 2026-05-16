"""
Tests for Bridge._collapse_metric_backlog_on_timeout — the slow-link
death-spiral mitigation that drops accumulated metric snapshots when
a /update/ POST times out.
"""
from amplify.agent.managers.bridge import Bridge


def _bridge_with_payload(metrics_snapshots, events=None, configs=None, meta=None):
    """Build a Bridge with a synthetic payload (skip __init__'s context deps)."""
    b = Bridge.__new__(Bridge)
    b.payload = {
        "meta": list(meta or []),
        "metrics": list(metrics_snapshots),
        "events": list(events or []),
        "configs": list(configs or []),
    }
    return b


def test_collapse_no_op_when_empty():
    b = _bridge_with_payload([])
    assert b._collapse_metric_backlog_on_timeout() == 0
    assert b.payload["metrics"] == []


def test_collapse_no_op_when_single_snapshot():
    snap = {"object": {"id": 1}, "metrics": {"a": [1, 2]}}
    b = _bridge_with_payload([snap])
    assert b._collapse_metric_backlog_on_timeout() == 0
    assert b.payload["metrics"] == [snap]


def test_collapse_keeps_only_most_recent():
    snaps = [{"object": {"id": i}, "metrics": {"a": [i]}} for i in range(5)]
    b = _bridge_with_payload(snaps)
    dropped = b._collapse_metric_backlog_on_timeout()
    assert dropped == 4
    assert b.payload["metrics"] == [snaps[-1]]


def test_collapse_preserves_other_buckets():
    snaps = [{"object": {"id": i}} for i in range(3)]
    meta = [{"object": {"type": "system"}}]
    events = [{"event": "x"}, {"event": "y"}]
    configs = [{"config": "z"}]
    b = _bridge_with_payload(snaps, events=events, configs=configs, meta=meta)
    b._collapse_metric_backlog_on_timeout()
    assert b.payload["meta"] == meta
    assert b.payload["events"] == events
    assert b.payload["configs"] == configs
    assert len(b.payload["metrics"]) == 1
