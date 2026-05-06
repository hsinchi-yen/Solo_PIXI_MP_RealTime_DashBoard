"""
UI-level tests for RealtimeSplitterApp that can run headlessly.
Uses pytest-qt or QApplication in offscreen mode.
"""
import os
import sys
import time
import pytest

# Run Qt in offscreen mode (no display required)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtCore import QTimer
    _QT_AVAILABLE = True
except ImportError:
    _QT_AVAILABLE = False

pytestmark = pytest.mark.skipif(not _QT_AVAILABLE, reason="PyQt5 not installed")


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication(sys.argv[:1])
    yield app


@pytest.fixture
def app_window(qapp, tmp_path):
    sys.path.insert(0, str(os.path.join(os.path.dirname(__file__), '..', 'Reference_app')))
    from realtime_splitter_app import RealtimeSplitterApp
    win = RealtimeSplitterApp()
    win.show()
    qapp.processEvents()
    yield win
    win.close()
    qapp.processEvents()


# ── _save_all_settings must not block the UI thread ───────────────────────────

class TestSaveSettingsNonBlocking:
    def test_save_returns_quickly(self, app_window, qapp):
        """_save_all_settings should return in well under 100 ms.
        The old code called time.sleep(0.5) on the main thread — that would fail this test.
        """
        t0 = time.monotonic()
        app_window._save_all_settings()
        qapp.processEvents()
        elapsed_ms = (time.monotonic() - t0) * 1000
        assert elapsed_ms < 100, (
            f"_save_all_settings blocked the UI thread for {elapsed_ms:.0f} ms "
            f"(expected < 100 ms; time.sleep on main thread is not acceptable)"
        )

    def test_save_button_label_restored_after_timer(self, app_window, qapp):
        """After save the button should show '✓', then revert to original after the timer fires."""
        orig = app_window.btn_save_station.text()
        app_window._save_all_settings()
        qapp.processEvents()
        assert app_window.btn_save_station.text() == "✓"

        # Let the 500 ms timer fire
        QTimer.singleShot(600, qapp.quit)
        qapp.exec_()
        assert app_window.btn_save_station.text() == orig
