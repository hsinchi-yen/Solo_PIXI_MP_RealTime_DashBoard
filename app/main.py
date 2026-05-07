import asyncio
import json
import ipaddress
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
from .uploader import uploader_manager, load_db_config, save_db_config, get_dsn, async_test_connection

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"
MISSION_FILE = Path(__file__).parent.parent / "config" / "mission.json"
WORK_ORDER_ROOT = Path("/run/media/nvme0n1p1")
WORK_ORDER_MIN_LEN = int(os.getenv("WORK_ORDER_MIN_LEN", "13"))
WORK_ORDER_MAX_LEN = int(os.getenv("WORK_ORDER_MAX_LEN", "16"))
WORK_ORDER_CACHE_TTL_SEC = 60

if WORK_ORDER_MIN_LEN > WORK_ORDER_MAX_LEN:
    WORK_ORDER_MIN_LEN, WORK_ORDER_MAX_LEN = WORK_ORDER_MAX_LEN, WORK_ORDER_MIN_LEN


def _norm_path(p: Path) -> str:
    return os.path.normcase(os.path.normpath(str(p)))


def _is_within(path: Path, root: Path) -> bool:
    try:
        return os.path.commonpath([_norm_path(path), _norm_path(root)]) == _norm_path(root)
    except ValueError:
        return False


def _allowed_roots() -> list[Path]:
    roots = [
        BASE_DIR.resolve(),
        config.paths.log_dir.resolve(),
        WORK_ORDER_ROOT.resolve(),
    ]
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


def _is_loopback_host(host: str) -> bool:
    host = (host or "").strip()
    if not host:
        return False
    if host == "localhost":
        return True
    if host.startswith("::ffff:"):
        host = host.split("::ffff:", 1)[1]
    host = host.split("%", 1)[0]
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _client_host(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for", "").split(",", 1)[0].strip()
    if xff:
        return xff
    x_real_ip = request.headers.get("x-real-ip", "").strip()
    if x_real_ip:
        return x_real_ip
    return request.client.host if request.client else ""


def _is_local_request(request: Request) -> bool:
    host_header = request.headers.get("host", "").strip()
    host_name = host_header.split(":", 1)[0] if host_header else ""
    if _is_loopback_host(host_name):
        return True
    return _is_loopback_host(_client_host(request))


def _require_localhost(request: Request) -> JSONResponse | None:
    if _is_local_request(request):
        return None
    return JSONResponse(
        {"error": "modification allowed only from localhost"},
        status_code=403,
    )


# DB settings are accessible from localhost AND the configured LAN subnet.
# Override via env var DB_ALLOW_CIDR (e.g. "192.168.1.0/24").
_DB_ALLOW_CIDR = os.getenv("DB_ALLOW_CIDR", "10.0.0.0/8")
try:
    _DB_ALLOW_NET = ipaddress.ip_network(_DB_ALLOW_CIDR, strict=False)
except ValueError:
    _DB_ALLOW_NET = ipaddress.ip_network("10.0.0.0/8")


def _is_lan_db_request(request: Request) -> bool:
    if _is_local_request(request):
        return True
    raw = _client_host(request).split("%", 1)[0]
    if raw.startswith("::ffff:"):
        raw = raw[7:]
    try:
        return ipaddress.ip_address(raw) in _DB_ALLOW_NET
    except ValueError:
        return False


def _require_db_access(request: Request) -> JSONResponse | None:
    if _is_lan_db_request(request):
        return None
    return JSONResponse(
        {"error": "DB settings accessible only from localhost or LAN"},
        status_code=403,
    )

config = load_config()
state = DashboardState(config)
sse_manager = SSEManager(max_connections=config.server.max_sse_connections)
_observer = None
_scan_task: asyncio.Task | None = None
_work_order_cache: list[str] = []
_work_order_cache_ts: float = 0.0


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


def _extract_work_order_from_dirname(name: str) -> str | None:
    text = (name or "").strip()
    if not text:
        return None

    lb = text.find("[")
    rb = text.find("]", lb + 1) if lb >= 0 else -1
    if lb >= 0 and rb > lb:
        text = text[lb + 1:rb].strip()

    text_len = len(text)
    if text_len < WORK_ORDER_MIN_LEN or text_len > WORK_ORDER_MAX_LEN:
        return None
    return text


def _scan_work_orders() -> list[str]:
    if not WORK_ORDER_ROOT.is_dir():
        return []

    names: set[str] = set()
    for child in WORK_ORDER_ROOT.iterdir():
        if not child.is_dir():
            continue
        wo = _extract_work_order_from_dirname(child.name)
        if wo:
            names.add(wo)
    return sorted(names)


def _get_work_orders(refresh: bool = False) -> list[str]:
    global _work_order_cache, _work_order_cache_ts

    now = time.time()
    if refresh or (now - _work_order_cache_ts) > WORK_ORDER_CACHE_TTL_SEC:
        _work_order_cache = _scan_work_orders()
        _work_order_cache_ts = now
    return list(_work_order_cache)


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


@app.get("/api/access")
async def access(request: Request):
    return JSONResponse(
        {
            "can_modify": _is_local_request(request),
            "client_host": _client_host(request),
        }
    )


@app.get("/api/db-access")
async def db_access(request: Request):
    return JSONResponse(
        {
            "can_db": _is_lan_db_request(request),
            "client_host": _client_host(request),
        }
    )


@app.get("/api/work-orders")
async def work_orders(request: Request, refresh: int = 0):
    denied = _require_localhost(request)
    if denied:
        return denied
    items = _get_work_orders(refresh=bool(refresh))
    return JSONResponse(
        {
            "items": items,
            "source_root": str(WORK_ORDER_ROOT),
            "length_min": WORK_ORDER_MIN_LEN,
            "length_max": WORK_ORDER_MAX_LEN,
            "cached_at": int(_work_order_cache_ts),
        }
    )


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
async def set_log_dir(request: Request, body: dict):
    global _observer, _scan_task

    denied = _require_localhost(request)
    if denied:
        return denied

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
async def log_sweep(request: Request):
    denied = _require_localhost(request)
    if denied:
        return denied

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


@app.get("/api/mission")
async def get_mission():
    if not MISSION_FILE.exists():
        return JSONResponse({})
    try:
        with MISSION_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return JSONResponse({})
        return JSONResponse(data)
    except Exception as e:
        logger.warning("failed to read mission config: %s", e)
        return JSONResponse({})


@app.post("/api/mission")
async def save_mission(request: Request, body: dict):
    denied = _require_localhost(request)
    if denied:
        return denied

    if not isinstance(body, dict):
        return JSONResponse({"error": "invalid payload"}, status_code=400)

    payload = {
        "wo": str(body.get("wo", "")),
        "qty": int(body.get("qty", 100) or 100),
        "log_dir": str(body.get("log_dir", "")),
    }
    if payload["qty"] < 1:
        payload["qty"] = 1

    try:
        MISSION_FILE.parent.mkdir(parents=True, exist_ok=True)
        with MISSION_FILE.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        return JSONResponse({"ok": True})
    except Exception as e:
        logger.error("failed to save mission config: %s", e)
        return JSONResponse({"error": "failed to save mission"}, status_code=500)


@app.delete("/api/mission")
async def clear_mission(request: Request):
    denied = _require_localhost(request)
    if denied:
        return denied
    try:
        if MISSION_FILE.exists():
            MISSION_FILE.unlink()
        return JSONResponse({"ok": True})
    except Exception as e:
        logger.error("failed to clear mission config: %s", e)
        return JSONResponse({"error": "failed to clear mission"}, status_code=500)


@app.get("/api/browse-dir")
async def browse_dir(request: Request, path: str = ""):
    denied = _require_localhost(request)
    if denied:
        return denied

    if not path or not path.strip():
        # Prefer the work-order mount as browse entry when it exists.
        # This lets users pick WO/rawlogs paths directly on deployed Linux targets.
        if WORK_ORDER_ROOT.is_dir() and _is_allowed_path(WORK_ORDER_ROOT.resolve()):
            p = WORK_ORDER_ROOT
        else:
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


# --- DB Uploader APIs ---

@app.get("/api/db-settings")
async def get_db_settings(request: Request):
    denied = _require_db_access(request)
    if denied:
        return denied
    return JSONResponse(load_db_config())


@app.post("/api/db-settings")
async def set_db_settings(request: Request, body: dict):
    denied = _require_db_access(request)
    if denied:
        return denied
    cfg = load_db_config()
    for k in ["DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASS"]:
        if k in body:
            cfg[k] = str(body[k])
    try:
        save_db_config(cfg)
    except Exception as e:
        logger.error("Failed to write .env: %s", e)
        return JSONResponse({"error": str(e)}, status_code=500)
    return JSONResponse({"ok": True})


@app.api_route("/api/db-test", methods=["GET", "POST"])
async def test_db_connection(request: Request):
    denied = _require_db_access(request)
    if denied:
        return denied

    dsn: str | None = None
    if request.method == "POST":
        try:
            body = await request.json()
            if isinstance(body, dict) and body.get("DB_HOST"):
                dsn = (
                    f"postgresql://{body.get('DB_USER', '')}:{body.get('DB_PASS', '')}"
                    f"@{body.get('DB_HOST', '')}:{body.get('DB_PORT', '5432')}/{body.get('DB_NAME', '')}"
                )
        except Exception:
            pass

    try:
        await async_test_connection(dsn)
        return JSONResponse({"ok": True})
    except ImportError:
        return JSONResponse({"error": "asyncpg is not installed"}, status_code=500)
    except Exception as e:
        msg = str(e) or f"{type(e).__name__}: connection failed"
        return JSONResponse({"error": msg}, status_code=500)


@app.post("/api/upload")
async def trigger_upload(request: Request, body: dict):
    denied = _require_db_access(request)
    if denied:
        return denied
    wo = body.get("wo")
    if not wo:
        return JSONResponse({"error": "WO is required"}, status_code=400)
    target_path = config.paths.log_dir / wo
    if not target_path.is_dir():
        return JSONResponse({"error": f"Directory not found: {target_path}"}, status_code=404)
    started = uploader_manager.start_manual_upload(str(target_path))
    if started:
        return JSONResponse({"ok": True, "message": "Upload started"})
    return JSONResponse({"error": "An upload is already running"}, status_code=400)


@app.post("/api/auto-upload")
async def trigger_auto_upload(request: Request, body: dict):
    denied = _require_db_access(request)
    if denied:
        return denied
    wo = body.get("wo")
    if not wo:
        return JSONResponse({"error": "WO is required"}, status_code=400)
    target_path = config.paths.log_dir / wo
    if not target_path.is_dir() and not uploader_manager.auto_upload_running:
        return JSONResponse({"error": f"Directory not found: {target_path}"}, status_code=404)
    is_running = uploader_manager.toggle_auto_upload(str(target_path))
    return JSONResponse({"ok": True, "auto_running": is_running})


@app.get("/api/upload-status")
async def get_upload_status(request: Request):
    return JSONResponse(uploader_manager.get_status())

