import asyncio
import logging
from collections import OrderedDict
from pathlib import Path

from watchdog.events import (
    FileCreatedEvent,
    FileDeletedEvent,
    FileModifiedEvent,
    FileMovedEvent,
    FileSystemEventHandler,
)
from watchdog.observers.polling import PollingObserver

from . import parser
from .config import WatcherConfig
from .sse import SSEManager
from .state import DashboardState

logger = logging.getLogger(__name__)


class _BoundedSeenCache:
    """LRU path cache used to suppress duplicate file events with bounded memory."""

    def __init__(self, max_items: int):
        self._max_items = max(1, max_items)
        self._items: OrderedDict[str, None] = OrderedDict()

    def add(self, path: str) -> bool:
        if path in self._items:
            self._items.move_to_end(path)
            return False
        self._items[path] = None
        if len(self._items) > self._max_items:
            self._items.popitem(last=False)
        return True

    def discard(self, path: str) -> None:
        self._items.pop(path, None)


class _LogFileHandler(FileSystemEventHandler):
    """
    Watchdog event handler that ingests new .txt log files.

    Uses PollingObserver (cross-platform) so the same code works on:
      - Windows (native uvicorn)
      - Linux (Docker container with Windows bind-mount)
      - Any NFS or remote filesystem

    Handles two creation patterns used by test stations:
      on_created  – file written directly with its final name
      on_moved    – file written as a temp, then atomically renamed to final name
    """

    def __init__(
        self,
        log_dir: str,
        state: DashboardState,
        sse: SSEManager,
        loop: asyncio.AbstractEventLoop,
        parse_delay: float,
        seen_cache_max: int,
    ):
        super().__init__()
        self._log_dir = log_dir
        self._state = state
        self._sse = sse
        self._loop = loop
        self._parse_delay = parse_delay
        self._rescan_delay = max(0.5, parse_delay)
        self._rescan_task: asyncio.Task | None = None
        self._seen = _BoundedSeenCache(seen_cache_max)

    def _schedule(self, raw_path: str) -> None:
        path = str(Path(raw_path).resolve())
        if Path(path).suffix.lower() != ".txt":
            return
        if not self._seen.add(path):
            return
        asyncio.run_coroutine_threadsafe(
            _delayed_handle(path, self._parse_delay, self._state, self._sse),
            self._loop,
        )

    def _schedule_rescan(self) -> None:
        asyncio.run_coroutine_threadsafe(self._debounced_rescan(), self._loop)

    def on_created(self, event: FileCreatedEvent) -> None:
        if not event.is_directory:
            self._schedule(event.src_path)
            if Path(event.src_path).suffix.lower() == ".txt":
                self._schedule_rescan()

    def on_moved(self, event: FileMovedEvent) -> None:
        # Some test tools write to a temp file then rename to the final path
        if not event.is_directory:
            self._schedule(event.dest_path)
            if Path(event.dest_path).suffix.lower() == ".txt":
                self._schedule_rescan()

    def on_modified(self, event: FileModifiedEvent) -> None:
        if not event.is_directory and Path(event.src_path).suffix.lower() == ".txt":
            self._schedule_rescan()

    def on_deleted(self, event: FileDeletedEvent) -> None:
        if not event.is_directory:
            path = str(Path(event.src_path).resolve())
            self._seen.discard(path)
            if Path(path).suffix.lower() == ".txt":
                self._schedule_rescan()

    async def _debounced_rescan(self) -> None:
        if self._rescan_task and not self._rescan_task.done():
            self._rescan_task.cancel()
        self._rescan_task = asyncio.create_task(self._run_rescan())

    async def _run_rescan(self) -> None:
        try:
            if self._rescan_delay > 0:
                await asyncio.sleep(self._rescan_delay)
            await _rescan_all(self._log_dir, self._state, self._sse)
        except asyncio.CancelledError:
            pass


async def _delayed_handle(
    path: str, delay: float, state: DashboardState, sse: SSEManager
) -> None:
    """Wait for the test station to finish writing, then parse and broadcast."""
    if delay > 0:
        await asyncio.sleep(delay)
    await _handle_new_file(path, state, sse)


async def _handle_new_file(
    filepath: str, state: DashboardState, sse: SSEManager
) -> None:
    record = parser.parse(filepath)
    if record is None:
        return

    await state.ingest(record)

    # KPI / chart updates are handled by _rescan_all (triggered via _schedule_rescan).
    # Here we only push the immediate table-row and optional stop alert.
    await sse.broadcast(
        "new_record",
        {
            "station_id":   record["station_id"],
            "mac1":         record["mac1"],
            "mac2":         record["mac2"],
            "result":       record["result"],
            "time":         record["datetime"][11:19],
            "duration":     record["duration"],
            "failed_items": record["failed_items"],
            "fixture_id":   record["fixture_id"],
        },
    )

    if record["result"] == "STOP":
        await sse.broadcast(
            "stop_alert",
            {
                "mac1":       record["mac1"],
                "mac2":       record["mac2"],
                "time":       record["datetime"][11:19],
                "fixture_id": record["fixture_id"],
            },
        )


async def _rescan_all(log_dir: str, state: DashboardState, sse: SSEManager) -> None:
    p = Path(log_dir)
    if not p.is_dir():
        return
    files = sorted(p.glob("*.txt"), key=lambda f: f.name)
    records = await asyncio.to_thread(lambda: [parser.parse(str(f)) for f in files])
    filtered = [r for r in records if r]
    # Sort by datetime (oldest first) so newest records end up in recent_records deque
    filtered_sorted = sorted(filtered, key=lambda r: r["datetime"])
    await state.rebuild(filtered_sorted)
    await sse.broadcast("init_complete", {})


def start_watcher(
    log_dir: str,
    state: DashboardState,
    sse: SSEManager,
    loop: asyncio.AbstractEventLoop,
    watcher_cfg: WatcherConfig | None = None,
):
    poll_interval = watcher_cfg.poll_interval if watcher_cfg else 2.0
    parse_delay = watcher_cfg.parse_delay if watcher_cfg else 1.0
    seen_cache_max = watcher_cfg.seen_cache_max if watcher_cfg else 10000

    observer = PollingObserver(timeout=poll_interval)
    handler = _LogFileHandler(log_dir, state, sse, loop, parse_delay, seen_cache_max)
    observer.schedule(handler, log_dir, recursive=False)
    observer.start()
    logger.info(
        "watching '%s' via PollingObserver (poll=%.1fs, parse_delay=%.1fs)",
        log_dir, poll_interval, parse_delay,
    )
    return observer
