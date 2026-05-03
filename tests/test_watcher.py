from app.watcher import _BoundedSeenCache


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
