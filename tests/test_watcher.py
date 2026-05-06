from app.watcher import _BoundedSeenCache
from app import watcher


def test_seen_cache_deduplicates_and_limits_size():
    cache = _BoundedSeenCache(max_items=3)

    assert cache.add("a.txt") is True
    assert cache.add("b.txt") is True
    assert cache.add("c.txt") is True
    assert cache.add("b.txt") is False  # duplicate should not reschedule

    # Add one new path; oldest LRU entry (a.txt) should be evicted
    assert cache.add("d.txt") is True

    assert cache.add("a.txt") is True  # no longer in cache after eviction
    assert cache.add("d.txt") is False


class _DummyState:
    def __init__(self):
        self.ingested = []

    async def ingest(self, record):
        self.ingested.append(record)


class _DummySSE:
    def __init__(self):
        self.events = []

    async def broadcast(self, event_type, payload):
        self.events.append((event_type, payload))


async def test_handle_new_file_broadcasts_station_id(monkeypatch):
    rec = {
        "filename": "5101-260129012_20260417_090000_AABBCC001122_AABBCC001123_PASS.txt",
        "station_id": "5101-260129012",
        "fixture_id": "IQ112EA2387",
        "datetime": "2026-04-17T09:00:00",
        "mac1": "AABBCC001122",
        "mac2": "AABBCC001123",
        "result": "PASS",
        "duration": "00:10.0",
        "failed_items": [],
    }
    monkeypatch.setattr(watcher.parser, "parse", lambda _: rec)

    state = _DummyState()
    sse = _DummySSE()
    await watcher._handle_new_file("dummy.txt", state, sse)

    assert state.ingested == [rec]
    assert sse.events
    event_type, payload = sse.events[0]
    assert event_type == "new_record"
    assert payload["station_id"] == "5101-260129012"
