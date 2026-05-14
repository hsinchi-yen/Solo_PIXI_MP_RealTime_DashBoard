import asyncio
import json
import ipaddress
import logging
import os
import re as _re
import time
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4
import socket
import struct

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .config import BASE_DIR, load_config, save_log_dir
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
WORK_ORDER_ALT_ROOT = Path("/nvme0n1p1")
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
    try:
        if WORK_ORDER_ALT_ROOT.exists():
            roots.append(WORK_ORDER_ALT_ROOT.resolve())
    except OSError:
        pass
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

# 系統狀態快取 (供 CPU 計算使用)
_last_cpu_stats = None


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


def _find_wo_dir(wo: str) -> Path | None:
    """Return the first directory under WORK_ORDER_ROOT whose name matches wo."""
    if not WORK_ORDER_ROOT.is_dir():
        return None
    for child in WORK_ORDER_ROOT.iterdir():
        if child.is_dir() and _extract_work_order_from_dirname(child.name) == wo:
            return child
    return None


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

    def _dt_sort_key(f: Path) -> str:
        parts = f.stem.split("_")
        for i, part in enumerate(parts):
            if len(part) == 8 and part.isdigit() and i + 1 < len(parts):
                if len(parts[i + 1]) == 6 and parts[i + 1].isdigit():
                    return part + parts[i + 1]  # YYYYMMDDHHMMSS
        return f.name

    files = sorted(p.glob("*.txt"), key=_dt_sort_key)
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


def _static_version(filename: str) -> str:
    """Return mtime-based version string for a frontend file."""
    try:
        return str(int((FRONTEND_DIR / filename).stat().st_mtime))
    except OSError:
        return "0"


@app.get("/")
async def root():
    html_path = FRONTEND_DIR / "index.html"
    try:
        html = html_path.read_text(encoding="utf-8")
        html = _re.sub(
            r'(style\.css\?v=)\d+',
            lambda m: m.group(1) + _static_version("style.css"),
            html,
        )
        html = _re.sub(
            r'(dashboard\.js\?v=)\d+',
            lambda m: m.group(1) + _static_version("dashboard.js"),
            html,
        )
        return HTMLResponse(content=html)
    except OSError:
        return FileResponse(html_path)


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


@app.get("/api/path-health")
async def path_health(wo: str = ""):
    wo_root = WORK_ORDER_ROOT.resolve()
    rawlogs_root = (WORK_ORDER_ROOT / "rawlogs").resolve()
    log_dir = config.paths.log_dir.resolve()
    wo_name = (wo or "").strip()

    # Use _find_wo_dir so bracket-named dirs (e.g. [5101-xxx]) are resolved
    # correctly — consistent with how /api/upload resolves WO directories.
    if wo_name:
        wo_dir = _find_wo_dir(wo_name)
        wo_path_exists = wo_dir is not None
        wo_path_str = str(wo_dir) if wo_dir else str(wo_root / wo_name)
    else:
        wo_path_exists = False
        wo_path_str = ""

    return JSONResponse(
        {
            "wo_root": str(wo_root),
            "wo_root_exists": wo_root.is_dir(),
            "rawlogs_root": str(rawlogs_root),
            "rawlogs_root_exists": rawlogs_root.is_dir(),
            "log_dir": str(log_dir),
            "log_dir_exists": log_dir.is_dir(),
            "wo": wo_name,
            "wo_path": wo_path_str,
            "wo_path_exists": wo_path_exists,
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

        # Persist the new path to settings.toml so it survives restarts
        try:
            save_log_dir(p)
        except Exception as exc:
            logger.warning("could not persist log_dir to settings.toml: %s", exc)

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

    # Auto-create WO directory when it doesn't exist yet (custom WO entry)
    wo_name = payload["wo"].strip()
    wo_dir_created = False
    if wo_name and WORK_ORDER_ROOT.is_dir():
        if _find_wo_dir(wo_name) is None:
            new_wo_dir = WORK_ORDER_ROOT / wo_name
            try:
                new_wo_dir.mkdir(parents=True, exist_ok=True)
                wo_dir_created = True
                logger.info("auto-created WO directory: %s", new_wo_dir)
                global _work_order_cache_ts
                _work_order_cache_ts = 0.0  # invalidate WO list cache
            except OSError as exc:
                logger.warning("could not create WO directory %s: %s", new_wo_dir, exc)

    try:
        MISSION_FILE.parent.mkdir(parents=True, exist_ok=True)
        with MISSION_FILE.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        return JSONResponse({"ok": True, "wo_dir_created": wo_dir_created})
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
    target_path = _find_wo_dir(wo)
    if target_path is None or not target_path.is_dir():
        return JSONResponse({"error": f"WO directory not found: {wo}"}, status_code=404)
    started = uploader_manager.start_manual_upload(str(target_path))
    if started:
        return JSONResponse({"ok": True, "message": "Upload started", "path": str(target_path)})
    return JSONResponse({"error": "An upload is already running"}, status_code=400)


@app.post("/api/auto-upload")
async def trigger_auto_upload(request: Request, body: dict):
    denied = _require_db_access(request)
    if denied:
        return denied
    wo = body.get("wo")
    if not wo:
        return JSONResponse({"error": "WO is required"}, status_code=400)
    target_path = _find_wo_dir(wo)
    if target_path is None and not uploader_manager.auto_upload_running:
        return JSONResponse({"error": f"WO directory not found: {wo}"}, status_code=404)
    is_running = uploader_manager.toggle_auto_upload(str(target_path) if target_path else "")
    return JSONResponse({"ok": True, "auto_running": is_running, "path": str(target_path) if target_path else ""})


@app.get("/api/upload-status")
async def get_upload_status(request: Request):
    return JSONResponse(uploader_manager.get_status())


@app.get("/api/system-metrics")
async def get_system_metrics(request: Request):
    global _last_cpu_stats
    metrics = {
        "eth0_ip": "N/A",
        "cpu_usage": "0%",
        "free_mem": "N/A",
        "cpu_temp": "N/A"
    }

    # 1. 取得 eth0 IP
    try:
        import fcntl
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        ifname = b'eth0'
        # SIOCGIFADDR = 0x8915
        ip_bytes = fcntl.ioctl(
            s.fileno(),
            0x8915,
            struct.pack('256s', ifname[:15])
        )[20:24]
        metrics["eth0_ip"] = socket.inet_ntoa(ip_bytes)
    except Exception:
        metrics["eth0_ip"] = "N/A"

    # 2. 計算 CPU 使用率 (讀取 /proc/stat)
    try:
        stat_path = '/host/proc/stat' if os.path.exists('/host/proc/stat') else '/proc/stat'
        with open(stat_path, 'r') as f:
            lines = f.readlines()
        
        cpu_line = next((line for line in lines if line.startswith('cpu ')), None)
        if cpu_line:
            parts = cpu_line.split()
            # user, nice, system, idle, iowait, irq, softirq, steal, guest, guest_nice
            # idle_time = idle + iowait
            # non_idle_time = user + nice + system + irq + softirq + steal
            # total_time = idle_time + non_idle_time
            idle_time = float(parts[4]) + float(parts[5])
            non_idle_time = float(parts[1]) + float(parts[2]) + float(parts[3]) + float(parts[6]) + float(parts[7]) + float(parts[8])
            total_time = idle_time + non_idle_time

            if _last_cpu_stats:
                prev_idle, prev_total = _last_cpu_stats
                totald = total_time - prev_total
                idled = idle_time - prev_idle
                
                if totald > 0:
                    cpu_usage = 100.0 * (totald - idled) / totald
                    metrics["cpu_usage"] = f"{cpu_usage:.1f}%"
            
            _last_cpu_stats = (idle_time, total_time)
    except Exception:
        metrics["cpu_usage"] = "N/A"

    # 3. 取得 Free Memory (讀取 /proc/meminfo)
    try:
        meminfo_path = '/host/proc/meminfo' if os.path.exists('/host/proc/meminfo') else '/proc/meminfo'
        with open(meminfo_path, 'r') as f:
            meminfo = f.read()
            
        mem_available_line = next((line for line in meminfo.splitlines() if line.startswith('MemAvailable:')), None)
        if mem_available_line:
            kb = int(mem_available_line.split()[1])
            if kb > 1024 * 1024:
                metrics["free_mem"] = f"{kb / (1024 * 1024):.1f}G"
            else:
                metrics["free_mem"] = f"{kb / 1024:.0f}M"
        else:
            # Fallback to MemFree + Buffers + Cached if MemAvailable is missing
            mem_free = next((int(line.split()[1]) for line in meminfo.splitlines() if line.startswith('MemFree:')), 0)
            buffers = next((int(line.split()[1]) for line in meminfo.splitlines() if line.startswith('Buffers:')), 0)
            cached = next((int(line.split()[1]) for line in meminfo.splitlines() if line.startswith('Cached:')), 0)
            kb = mem_free + buffers + cached
            if kb > 0:
                if kb > 1024 * 1024:
                    metrics["free_mem"] = f"{kb / (1024 * 1024):.1f}G"
                else:
                    metrics["free_mem"] = f"{kb / 1024:.0f}M"
    except Exception:
        metrics["free_mem"] = "N/A"

    # 4. 取得 CPU 溫度
    try:
        temp_path = '/host/sys/devices/virtual/thermal/thermal_zone0/temp' if os.path.exists('/host/sys/devices/virtual/thermal/thermal_zone0/temp') else '/sys/devices/virtual/thermal/thermal_zone0/temp'
        with open(temp_path, 'r') as f:
            temp_raw = f.read().strip()
            temp_c = float(temp_raw) / 1000.0
            metrics["cpu_temp"] = f"{temp_c:.1f}°C"
    except Exception:
        metrics["cpu_temp"] = "N/A"

    return JSONResponse(metrics)

