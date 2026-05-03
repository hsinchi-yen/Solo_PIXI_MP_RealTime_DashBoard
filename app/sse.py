import asyncio
import logging

logger = logging.getLogger(__name__)


class TooManyConnectionsError(Exception):
    pass


class SSEManager:
    def __init__(self, max_connections: int = 20):
        self._clients: dict[str, asyncio.Queue] = {}
        self._max = max_connections
        self._pending_stats_task: asyncio.Task | None = None

    def register(self, client_id: str, queue: asyncio.Queue) -> None:
        if len(self._clients) >= self._max:
            raise TooManyConnectionsError(f"max {self._max} connections reached")
        self._clients[client_id] = queue
        logger.info("SSE client %s connected (%d total)", client_id[:8], len(self._clients))

    def unregister(self, client_id: str) -> None:
        self._clients.pop(client_id, None)
        logger.info("SSE client %s disconnected (%d remaining)", client_id[:8], len(self._clients))

    async def broadcast(self, event_type: str, data: dict) -> None:
        if not self._clients:
            return
        dead = []
        for cid, q in self._clients.items():
            try:
                q.put_nowait({"type": event_type, "data": data})
            except asyncio.QueueFull:
                dead.append(cid)
        for cid in dead:
            logger.warning("client %s queue full, disconnecting", cid[:8])
            self.unregister(cid)

    async def broadcast_debounced(self, event_type: str, data: dict, delay: float = 0.25) -> None:
        """Coalesce rapid broadcasts: only the last event fires after ``delay`` s.

        When many log files arrive at once (e.g., bulk-copy or polling scan), this
        prevents the browser from receiving dozens of events in a second, reducing
        CPU load on the SoC client.
        """
        t = self._pending_stats_task
        if t is not None and not t.done():
            t.cancel()
        self._pending_stats_task = asyncio.create_task(
            self._emit_after_delay(event_type, data, delay)
        )

    async def _emit_after_delay(self, event_type: str, data: dict, delay: float) -> None:
        try:
            await asyncio.sleep(delay)
            await self.broadcast(event_type, data)
        except asyncio.CancelledError:
            pass

    @property
    def connection_count(self) -> int:
        return len(self._clients)
