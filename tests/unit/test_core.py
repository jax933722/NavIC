from core.eventbus import Event, InMemoryEventBus
from core.ids import content_hash, content_hash_str, new_trace_id


def test_content_hash_stable():
    assert content_hash(b"abc") == content_hash(b"abc")
    assert content_hash_str("abc") == content_hash(b"abc")
    assert content_hash(b"abc") != content_hash(b"abd")


def test_trace_id_unique():
    assert new_trace_id() != new_trace_id()


def test_eventbus_delivers_and_dedupes():
    bus = InMemoryEventBus()
    seen: list[str] = []
    bus.subscribe("documents.parsed", lambda e: seen.append(e.event_id))

    ev = Event(type="documents.parsed", payload={"x": 1}, idempotency_key="hash-1")
    bus.publish(ev)
    bus.publish(ev)  # replay with same key -> deduped (NFR-3)

    assert len(seen) == 1
    assert len(bus.published) == 1


def test_event_envelope_shape():
    ev = Event(type="raw.fetched", payload={"url": "x"}, idempotency_key="k")
    d = ev.to_dict()
    assert d["type"] == "raw.fetched"
    assert d["schema_version"] == 1
    assert "trace_id" in d and "idempotency_key" in d and "occurred_at" in d
