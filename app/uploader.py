import asyncio
import os
import time
import logging
import threading
import importlib.util
from pathlib import Path

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent.parent
ENV_FILE = BASE_DIR / ".env"

# ── Config helpers ────────────────────────────────────────────────────────────

def load_db_config() -> dict:
    config = {
        "DB_HOST": "10.20.31.40",
        "DB_PORT": "5433",
        "DB_NAME": "pixi_test",
        "DB_USER": "pixi",
        "DB_PASS": "pixipass",
    }
    if ENV_FILE.exists():
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    config[k.strip()] = v.strip()
    return config


def save_db_config(cfg: dict) -> None:
    ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(ENV_FILE, "w", encoding="utf-8") as f:
        for k, v in cfg.items():
            f.write(f"{k}={v}\n")


def get_dsn() -> str:
    cfg = load_db_config()
    return (
        f"postgresql://{cfg['DB_USER']}:{cfg['DB_PASS']}"
        f"@{cfg['DB_HOST']}:{cfg['DB_PORT']}/{cfg['DB_NAME']}"
    )


# ── Async connection test (asyncpg — non-blocking) ────────────────────────────

async def async_test_connection(dsn: str | None = None) -> None:
    """Connect, run SELECT 1, then close. Raises on any failure."""
    import asyncpg  # noqa: F401 — import checked at call site in main.py
    conn = await asyncpg.connect(dsn or get_dsn(), timeout=4)
    try:
        await conn.fetchval("SELECT 1")
    finally:
        await conn.close()


# ── Parser loader ─────────────────────────────────────────────────────────────

def load_parser_module():
    parser_path = Path(__file__).parent / "module_log_parser.py"
    if not parser_path.exists():
        raise ImportError(
            f"Cannot find {parser_path}. "
            "Place module_log_parser.py in the app/ directory."
        )
    spec = importlib.util.spec_from_file_location(
        "solo_pixi_module_log_parser", str(parser_path)
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ── Background upload manager (psycopg2 in worker threads) ───────────────────

class UploaderManager:
    def __init__(self):
        self.auto_upload_running = False
        self.auto_thread = None
        self.manual_thread = None
        self.lock = threading.Lock()
        self.stats = {"uploaded": 0, "skipped": 0, "failed": 0}
        self.is_uploading = False

    def get_status(self) -> dict:
        with self.lock:
            return {
                "auto_running": self.auto_upload_running,
                "is_uploading": self.is_uploading,
                "stats": dict(self.stats),
            }

    def start_manual_upload(self, folder_path: str) -> bool:
        with self.lock:
            if self.is_uploading:
                return False
            self.is_uploading = True
            self.stats = {"uploaded": 0, "skipped": 0, "failed": 0}

        self.manual_thread = threading.Thread(
            target=self._manual_worker, args=(folder_path,), daemon=True
        )
        self.manual_thread.start()
        return True

    def _manual_worker(self, folder_path: str) -> None:
        try:
            self._process_folder(folder_path)
        finally:
            with self.lock:
                self.is_uploading = False

    def toggle_auto_upload(self, folder_path: str) -> bool:
        with self.lock:
            if self.auto_upload_running:
                self.auto_upload_running = False
                return False
            self.auto_upload_running = True
            self.auto_thread = threading.Thread(
                target=self._auto_worker, args=(folder_path,), daemon=True
            )
            self.auto_thread.start()
            return True

    def _auto_worker(self, folder_path: str) -> None:
        logger.info("Auto upload started for %s", folder_path)
        try:
            import psycopg2  # noqa: F401
        except ImportError:
            logger.error("psycopg2-binary is not installed — auto upload disabled")
            self.auto_upload_running = False
            return

        processed: set[str] = set()
        while self.auto_upload_running:
            try:
                if os.path.exists(folder_path):
                    self._process_folder(folder_path, processed_files=processed)
            except Exception as exc:
                logger.error("Auto upload error: %s", exc)
            time.sleep(1)
        logger.info("Auto upload stopped")

    def _process_folder(
        self, folder_path: str, processed_files: set | None = None
    ) -> None:
        try:
            import psycopg2
        except ImportError:
            logger.error("psycopg2-binary is not installed — upload skipped")
            return

        try:
            parser = load_parser_module()
        except Exception as exc:
            logger.error("Failed to load parser: %s", exc)
            return

        try:
            conn = psycopg2.connect(get_dsn(), connect_timeout=3)
        except Exception as exc:
            logger.error("DB connect failed: %s", exc)
            return

        path = Path(folder_path)
        if not path.is_dir():
            conn.close()
            return

        files = [
            f
            for f in path.iterdir()
            if f.is_file() and f.suffix.lower() == ".txt"
            and _parser_accepts(parser, f.name)
            and (processed_files is None or str(f) not in processed_files)
        ]

        if not files:
            conn.close()
            return

        uploaded = skipped = failed = 0
        for i, fpath in enumerate(files):
            if processed_files is not None and not self.auto_upload_running:
                break
            try:
                rec = parser.parse_log_file(str(fpath))
                if parser.insert_record(conn, rec):
                    uploaded += 1
                else:
                    skipped += 1
                if processed_files is not None:
                    processed_files.add(str(fpath))
            except Exception as exc:
                logger.error("Upload error for %s: %s", fpath.name, exc)
                failed += 1

            if (i + 1) % 10 == 0:
                try:
                    conn.commit()
                except Exception:
                    pass

        try:
            conn.commit()
            conn.close()
        except Exception:
            pass

        with self.lock:
            self.stats["uploaded"] += uploaded
            self.stats["skipped"] += skipped
            self.stats["failed"] += failed


def _parser_accepts(parser, fname: str) -> bool:
    for attr in ("FILENAME_RE", "LEGACY_FILENAME_RE", "FILENAME_RE_WO"):
        re_obj = getattr(parser, attr, None)
        if re_obj and re_obj.match(fname):
            return True
    return False


uploader_manager = UploaderManager()
