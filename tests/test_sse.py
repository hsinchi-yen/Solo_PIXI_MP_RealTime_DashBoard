"""Unit tests for SSEManager, including the debounce mechanism."""
import asyncio

import pytest

from app.sse import SSEManager, TooManyConnectionsError


@pytest.mark.asyncio
async def test_broadcast_delivers_to_registered_client():
    mgr = SSEManager(max_connections=5)
    q: asyncio.Queue = asyncio.Queue(maxsize=10)
    mgr.register("c1", q)

    await mgr.broadcast("test_event", {"key": "value"})

    assert not q.empty()
    item = q.get_nowait()
    assert item == {"type": "test_event", "data": {"key": "value"}}


@pytest.mark.asyncio
async def test_broadcast_skips_no_clients():
    """broadcast with no clients should not raise."""
    mgr = SSEManager()
    await mgr.broadcast("test_event", {"x": 1})  # must not raise


@pytest.mark.asyncio
async def test_too_many_connections():
    mgr = SSEManager(max_connections=2)
    mgr.register("c1", asyncio.Queue())
    mgr.register("c2", asyncio.Queue())
    with pytest.raises(TooManyConnectionsError):
        mgr.register("c3", asyncio.Queue())


@pytest.mark.asyncio
async def test_unregister_removes_client():
    mgr = SSEManager()
    q: asyncio.Queue = asyncio.Queue(maxsize=10)
    mgr.register("c1", q)
    mgr.unregister("c1")
    assert mgr.connection_count == 0
    # broadcast after unregister must not enqueue anything
    await mgr.broadcast("evt", {})
    assert q.empty()


@pytest.mark.asyncio
async def test_debounce_coalesces_rapid_calls():
    """Only the last payload should be delivered when calls arrive faster than delay."""
    mgr = SSEManager(max_connections=5)
    q: asyncio.Queue = asyncio.Queue(maxsize=20)
    mgr.register("c1", q)

    delay = 0.1  # 100 ms
    # Fire three rapid calls — first two should be cancelled
    await mgr.broadcast_debounced("stats_update", {"v": 1}, delay=delay)
    await mgr.broadcast_debounced("stats_update", {"v": 2}, delay=delay)
    await mgr.broadcast_debounced("stats_update", {"v": 3}, delay=delay)

    # Wait longer than delay to let the final task fire
    await asyncio.sleep(delay * 2.5)

    items = []
    while not q.empty():
        items.append(q.get_nowait())

    assert len(items) == 1, f"expected 1 delivery, got {len(items)}: {items}"
    assert items[0]["data"]["v"] == 3


@pytest.mark.asyncio
async def test_debounce_delivers_when_calls_spaced_apart():
    """When calls are spaced > delay apart, each one fires independently."""
    mgr = SSEManager(max_connections=5)
    q: asyncio.Queue = asyncio.Queue(maxsize=20)
    mgr.register("c1", q)

    delay = 0.05  # 50 ms
    await mgr.broadcast_debounced("stats_update", {"v": 1}, delay=delay)
    await asyncio.sleep(delay * 3)  # let first one fire
    await mgr.broadcast_debounced("stats_update", {"v": 2}, delay=delay)
    await asyncio.sleep(delay * 3)  # let second one fire

    items = []
    while not q.empty():
        items.append(q.get_nowait())

    assert len(items) == 2
    assert items[0]["data"]["v"] == 1
    assert items[1]["data"]["v"] == 2
