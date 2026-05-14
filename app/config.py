import re
import sys
from dataclasses import dataclass
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

BASE_DIR = Path(__file__).parent.parent


@dataclass
class PathsConfig:
    log_dir: Path


@dataclass
class ServerConfig:
    host: str
    port: int
    max_sse_connections: int


@dataclass
class WatcherConfig:
    poll_interval: float   # seconds between directory polls
    parse_delay: float     # seconds to wait after file detected before parsing
    seen_cache_max: int    # max remembered paths for duplicate suppression
    startup_scan_batch_size: int  # files parsed per startup batch


@dataclass
class DashboardConfig:
    recent_records_limit: int
    uph_window_minutes: int
    yield_warning_threshold: float
    yield_critical_threshold: float


@dataclass
class Config:
    paths: PathsConfig
    server: ServerConfig
    watcher: WatcherConfig
    dashboard: DashboardConfig


def save_log_dir(log_dir: Path, config_path: "str | Path | None" = None) -> None:
    """Persist log_dir back to settings.toml so it survives restarts."""
    if config_path is None:
        config_path = BASE_DIR / "config" / "settings.toml"
    p = Path(config_path)
    text = p.read_text(encoding="utf-8")
    new_line = f'log_dir = "{log_dir.as_posix()}"'
    text = re.sub(r"^log_dir\s*=\s*.+$", new_line, text, flags=re.MULTILINE)
    p.write_text(text, encoding="utf-8")


def load_config(path: str | None = None) -> Config:
    if path is None:
        path = BASE_DIR / "config" / "settings.toml"
    with open(path, "rb") as f:
        data = tomllib.load(f)

    log_dir = Path(data["paths"]["log_dir"])
    if not log_dir.is_absolute():
        log_dir = BASE_DIR / log_dir

    w = data.get("watcher", {})

    return Config(
        paths=PathsConfig(log_dir=log_dir),
        server=ServerConfig(
            host=data["server"]["host"],
            port=data["server"]["port"],
            max_sse_connections=data["server"]["max_sse_connections"],
        ),
        watcher=WatcherConfig(
            poll_interval=float(w.get("poll_interval", 2.0)),
            parse_delay=float(w.get("parse_delay", 1.0)),
            seen_cache_max=max(100, int(w.get("seen_cache_max", 10000))),
            startup_scan_batch_size=max(10, int(w.get("startup_scan_batch_size", 200))),
        ),
        dashboard=DashboardConfig(
            recent_records_limit=data["dashboard"]["recent_records_limit"],
            uph_window_minutes=data["dashboard"]["uph_window_minutes"],
            yield_warning_threshold=data["dashboard"]["yield_warning_threshold"],
            yield_critical_threshold=data["dashboard"]["yield_critical_threshold"],
        ),
    )
