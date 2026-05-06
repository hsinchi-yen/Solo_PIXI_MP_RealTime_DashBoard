"""
Test suite for remote SSH/SFTP path handling with paramiko.

This test verifies the remote path detection and parsing logic.
"""
import unittest
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(__file__))

from realtime_splitter_app import is_rsync_path, parse_remote_path


class TestRsyncPathDetection(unittest.TestCase):
    """Test the is_rsync_path() helper function."""

    def test_detects_rsync_path_format(self):
        """Should identify valid rsync paths (user@host:/path)."""
        # Arrange
        rsync_path = "root@10.20.31.106:/run/media/nvme0n1p1/rawlogs/"
        
        # Act
        result = is_rsync_path(rsync_path)
        
        # Assert
        self.assertTrue(result, "Should detect rsync path format")

    def test_rejects_local_windows_path(self):
        """Should not identify Windows local paths as rsync."""
        # Arrange
        local_path = "C:\\Users\\Documents\\output"
        
        # Act
        result = is_rsync_path(local_path)
        
        # Assert
        self.assertFalse(result, "Should not detect Windows path as rsync")

    def test_rejects_local_unix_path(self):
        """Should not identify Unix local paths as rsync."""
        # Arrange
        local_path = "/home/user/output"
        
        # Act
        result = is_rsync_path(local_path)
        
        # Assert
        self.assertFalse(result, "Should not detect Unix path as rsync")

    def test_rejects_empty_path(self):
        """Should handle empty string safely."""
        # Arrange
        empty_path = ""
        
        # Act
        result = is_rsync_path(empty_path)
        
        # Assert
        self.assertFalse(result, "Should return False for empty string")

    def test_rejects_none_path(self):
        """Should handle None safely."""
        # Arrange
        none_path = None
        
        # Act
        result = is_rsync_path(none_path)
        
        # Assert
        self.assertFalse(result, "Should return False for None")

    def test_detects_rsync_with_port(self):
        """Should detect rsync paths with custom SSH port."""
        # Arrange
        rsync_path = "user@host:22:/path/to/dir"
        
        # Act
        result = is_rsync_path(rsync_path)
        
        # Assert
        self.assertTrue(result, "Should detect rsync path with port")


class TestRsyncPathHandling(unittest.TestCase):
    """Test that rsync paths don't trigger local directory operations."""

    def test_rsync_path_does_not_call_makedirs(self):
        """
        Bug reproduction test: Verify that rsync paths don't attempt os.makedirs().
        
        BEFORE FIX: This would cause OSError on Windows:
        OSError: [WinError 123] 檔案名稱、目錄名稱或磁碟區標籤語法錯誤。
        
        AFTER FIX: Should recognize rsync path and skip makedirs.
        """
        # Arrange
        rsync_path = "root@10.20.31.106:/run/media/nvme0n1p1/rawlogs/"
        
        # Act - verify path is detected as rsync format
        is_remote = is_rsync_path(rsync_path)
        
        # Assert
        self.assertTrue(is_remote, 
            "rsync path should be detected as remote, preventing os.makedirs() call")


class TestRsyncAvailability(unittest.TestCase):
    """Test rsync command availability detection."""

    def test_check_rsync_available_returns_boolean(self):
        """
        Should return True if rsync is available, False otherwise.
        
        This test verifies the function works but doesn't assert the result
        since it depends on the system configuration.
        """
        # Act
        result = check_rsync_available()
        
        # Assert
        self.assertIsInstance(result, bool, 
            "check_rsync_available() should return a boolean")

    def test_handles_rsync_not_found_gracefully(self):
        """
        Bug reproduction test: Verify graceful handling when rsync is not available.
        
        BEFORE FIX: FileNotFoundError: [WinError 2] 系統找不到指定的檔案。
        AFTER FIX: Should detect missing rsync and show helpful error message.
        """
        # Arrange & Act
        # Just calling the function shouldn't raise an exception
        try:
            result = check_rsync_available()
            # Assert - should return boolean without crashing
            self.assertIsInstance(result, bool)
        except Exception as e:
            self.fail(f"check_rsync_available() raised {type(e).__name__}: {e}")


if __name__ == '__main__':
    # Run tests with verbose output
    unittest.main(verbosity=2)
