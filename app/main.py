import asyncio
import json
import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .config import BASE_DIR, load_config
from .parser import parse
from .sse import SSEManager, TooManyConnectionsError
from .state import DashboardState
from .watcher import start_watcher

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"


def _norm_path(p: Path) -> str:
    return os.path.normcase(os.path.normpath(str(p)))


def _is_within(path: Path, root: Path) -> bool:
    try:
        return os.path.commonpath([_norm_path(path), _norm_path(root)]) == _norm_path(root)
    except ValueError:
        return False


def _allowed_roots() -> list[Path]:
    roots = [BASE_DIR.resolve(), config.paths.log_dir.resolve()]
    seen = set()
    out = []
    for r in roots:
        key = _norm_path(r)
        if key not in seen:
            out.append(r)
            seen.add(key)
    return out


def _is_allowed_path(p: Path) -> bool:
    return any(_is_within(p, root) for root in _allowed_roots())

config = load_config()
state = DashboardState(config)
sse_manager = SSEManager(max_connections=config.server.max_sse_connections)
_observer = None
_scan_task: asyncio.Task | None = None


def _stop_observer(observer, timeout: float = 3.0) -> None:
    """Stop watchdog observer with a timeout so join() never hangs."""
    if observer is None:
        return
    try:
        observer.stop()
        observer.join(timeout=timeout)
        if observer.is_alive():
            logger.warning("observer did not stop within %.1fs — abandoning", timeout)
    except Exception as exc:
        logger.warning("error stopping observer: %s", exc)


async def _startup_scan(log_dir: str) -> None:
    p = Path(log_dir)
    if not p.is_dir():
        logger.warning("log_dir '%s' does not exist — skipping startup scan", log_dir)
        state.ready = True
        await sse_manager.broadcast("init_complete", {})
        return

    files = sorted(p.glob("*.txt"), key=lambda f: f.name)
    batch_size = config.watcher.startup_scan_batch_size
    state.scan_total = len(files)
    state.scan_current = 0
    logger.info(
        "startup scan: %d files in '%s' (batch_size=%d)",
        len(files),
        log_dir,
        batch_size,
    )

    for batch_start in range(0, len(files), batch_size):
        batch = files[batch_start:batch_start + batch_size]
        records = await asyncio.to_thread(
            lambda: [parse(str(f)) for f in batch]
        )
        for idx, record in enumerate(records, start=1):
            if record:
                await state.ingest(record)
            state.scan_current = batch_start + idx

        if sse_manager.connection_count > 0:
            await sse_manager.broadcast(
                "init_progress",
                {"current": state.scan_current, "total": state.scan_total},
            )
        # Always yield once per batch so SSE streams and HTTP handlers stay responsive.
        await asyncio.sleep(0)

    state.ready = True
    await sse_manager.broadcast("init_complete", {})
    logger.info("startup scan complete")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _observer, _scan_task
    loop = asyncio.get_running_loop()
    log_dir = str(config.paths.log_dir)
    app.state.config_lock = asyncio.Lock()

    _scan_task = asyncio.create_task(_startup_scan(log_dir))
    _observer = start_watcher(log_dir, state, sse_manager, loop, config.watcher)

    try:
        yield
    finally:
        # Cancel any in-progress startup scan
        if _scan_task and not _scan_task.done():
            _scan_task.cancel()
            try:
                await asyncio.wait_for(_scan_task, timeout=2.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

        # Stop file watcher (with timeout so it never hangs on Windows)
        _stop_observer(_observer)


app = FastAPI(lifespan=lifespan, title="PIXI Modules MP Monitoring DashBOARD")
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


def _get_config_lock() -> asyncio.Lock:
    lock = getattr(app.state, "config_lock", None)
    if lock is None:
        lock = asyncio.Lock()
        app.state.config_lock = lock
    return lock


@app.get("/")
async def root():
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/api/snapshot")
async def snapshot():
    return JSONResponse(state.get_snapshot())


@app.get("/api/stream")
async def sse_stream(request: Request):
    client_id = str(uuid4())
    queue: asyncio.Queue = asyncio.Queue(maxsize=100)

    try:
        sse_manager.register(client_id, queue)
    except TooManyConnectionsError as e:
        return JSONResponse({"error": str(e)}, status_code=503)

    async def event_generator():
        yield "retry: 3000\n\n"
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30)
                    data = json.dumps(event["data"], ensure_ascii=False)
                    yield f"event: {event['type']}\ndata: {data}\n\n"
                except asyncio.TimeoutError:
                    ts = int(time.time())
                    yield f"event: heartbeat\ndata: {{\"ts\":{ts}}}\n\n"
        finally:
            sse_manager.unregister(client_id)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.post("/api/config/log-dir")
async def set_log_dir(body: dict):
    global _observer, _scan_task

    raw_dir = body.get("log_dir")
    new_dir = raw_dir.strip() if isinstance(raw_dir, str) else ""
    if not new_dir:
        return JSONResponse({"error": "log_dir is required"}, status_code=400)

    p = Path(new_dir)
    if not p.is_absolute():
        p = BASE_DIR / p
    p = p.resolve()

    async with _get_config_lock():
        if not _is_allowed_path(p):
            return JSONResponse({"error": "log_dir not permitted"}, status_code=403)

        if not p.is_dir():
            return JSONResponse({"error": "directory not found"}, status_code=404)

        # Stop current watcher (with timeout to avoid hang on Windows)
        _stop_observer(_observer)
        _observer = None

        # Cancel any running scan task
        if _scan_task and not _scan_task.done():
            _scan_task.cancel()
            try:
                await asyncio.wait_for(asyncio.shield(_scan_task), timeout=2.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

        # Reset state and update config
        state.reset()
        config.paths.log_dir = p

        # Restart
        loop = asyncio.get_running_loop()
        _scan_task = asyncio.create_task(_startup_scan(str(p)))
        _observer = start_watcher(str(p), state, sse_manager, loop, config.watcher)

        await sse_manager.broadcast("reset", {"log_dir": str(p)})
        return JSONResponse({"ok": True, "log_dir": str(p)})


@app.post("/api/log-sweep")
async def log_sweep():
    log_dir = config.paths.log_dir.resolve()
    if not log_dir.is_dir():
        return JSONResponse({"error": "directory not found"}, status_code=404)
    count = 0
    for f in log_dir.glob("*.txt"):
        try:
            f.unlink()
            count += 1
        except OSError as e:
            logger.warning("sweep: could not delete %s: %s", f, e)
    state.reset()
    state.ready = True
    await sse_manager.broadcast("reset", {"log_dir": str(log_dir)})
    logger.info("log sweep: deleted %d files from '%s'", count, log_dir)
    return JSONResponse({"ok": True, "deleted": count})


@app.get("/api/config")
async def get_config():
    return JSONResponse({"log_dir": str(config.paths.log_dir)})


@app.get("/api/browse-dir")
async def browse_dir(path: str = ""):
    if not path or not path.strip():
        p = config.paths.log_dir
    else:
        p = Path(path.strip())
        if not p.is_absolute():
            p = BASE_DIR / p

    p = p.resolve()
    fallback = config.paths.log_dir.resolve()
    if not fallback.exists():
        fallback = BASE_DIR.resolve()

    if not p.exists() or not _is_allowed_path(p):
        p = fallback

    # Walk up until we find a valid directory
    while not p.is_dir() and p != p.parent:
        p = p.parent

    try:
        dirs = []
        for d in p.iterdir():
            if not d.is_dir() or d.name.startswith("."):
                continue
            try:
                if _is_allowed_path(d.resolve()):
                    dirs.append(d.name)
            except OSError:
                continue
        dirs = sorted(dirs, key=str.lower)
    except PermissionError:
        dirs = []

    parent_path = p.parent if p != p.parent else p
    if not _is_allowed_path(parent_path):
        parent_path = p
    parent = str(parent_path)
    return JSONResponse({"current": str(p), "parent": parent, "dirs": dirs})
