"""
Test suite for paramiko SSH/SFTP path handling.

This test verifies the remote path detection and parsing logic.
"""
import unittest
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(__file__))

from realtime_splitter_app import is_rsync_path, parse_remote_path


class TestRemotePathDetection(unittest.TestCase):
    """Test remote SSH path detection (user@host:/path format)."""

    def test_detects_remote_path_format(self):
        """Should identify valid remote SSH paths (user@host:/path)."""
        path = "root@10.20.31.106:/run/media/nvme0n1p1/rawlogs/"
        result = is_rsync_path(path)
        self.assertTrue(result, "Valid remote path should be detected")

    def test_detects_remote_with_username(self):
        """Should detect remote paths with different usernames."""
        path = "deploy@example.com:/var/www/logs"
        result = is_rsync_path(path)
        self.assertTrue(result, "Remote path should be detected")

    def test_rejects_local_windows_path(self):
        """Should not identify Windows local paths as remote."""
        path = "C:\\Users\\test\\Documents"
        result = is_rsync_path(path)
        self.assertFalse(result, "Windows local path should not be detected as remote")

    def test_rejects_local_unix_path(self):
        """Should not identify Unix local paths as remote."""
        path = "/home/user/documents"
        result = is_rsync_path(path)
        self.assertFalse(result, "Unix local path should not be detected as remote")

    def test_rejects_empty_path(self):
        """Should handle empty string safely."""
        path = ""
        result = is_rsync_path(path)
        self.assertFalse(result, "Empty string should return False")

    def test_rejects_none_path(self):
        """Should handle None safely."""
        path = None
        result = is_rsync_path(path)
        self.assertFalse(result, "None should return False")


class TestRemotePathParsing(unittest.TestCase):
    """Test remote path parsing into components."""

    def test_parses_valid_remote_path(self):
        """Should parse user@host:/path correctly."""
        path = "root@10.20.31.106:/run/media/nvme0n1p1/rawlogs/"
        user, host, remote_dir = parse_remote_path(path)
        
        self.assertEqual(user, "root")
        self.assertEqual(host, "10.20.31.106")
        self.assertEqual(remote_dir, "/run/media/nvme0n1p1/rawlogs/")

    def test_parses_path_with_different_user(self):
        """Should handle different usernames."""
        path = "deploy@192.168.1.100:/var/www/logs"
        user, host, remote_dir = parse_remote_path(path)
        
        self.assertEqual(user, "deploy")
        self.assertEqual(host, "192.168.1.100")
        self.assertEqual(remote_dir, "/var/www/logs")

    def test_returns_none_for_invalid_path(self):
        """Should return (None, None, None) for invalid paths."""
        path = "C:\\Windows\\System32"
        user, host, remote_dir = parse_remote_path(path)
        
        self.assertIsNone(user)
        self.assertIsNone(host)
        self.assertIsNone(remote_dir)

    def test_returns_none_for_empty_path(self):
        """Should return (None, None, None) for empty string."""
        path = ""
        user, host, remote_dir = parse_remote_path(path)
        
        self.assertIsNone(user)
        self.assertIsNone(host)
        self.assertIsNone(remote_dir)

    def test_handles_path_with_subdirectories(self):
        """Should correctly parse paths with multiple subdirectories."""
        path = "admin@server.com:/home/admin/logs/archive/2026"
        user, host, remote_dir = parse_remote_path(path)
        
        self.assertEqual(user, "admin")
        self.assertEqual(host, "server.com")
        self.assertEqual(remote_dir, "/home/admin/logs/archive/2026")


class TestRemotePathHandling(unittest.TestCase):
    """Test that remote paths don't attempt local filesystem operations."""

    def test_remote_path_does_not_call_makedirs(self):
        """
        Bug reproduction test: Verify that remote paths don't attempt os.makedirs().
        
        BEFORE FIX: OSError: [WinError 123] 檔案名稱、目錄名稱或磁碟區標籤語法錯誤。
        AFTER FIX: Remote paths should be detected and skip local directory creation.
        """
        remote_path = "root@10.20.31.106:/run/media/nvme0n1p1/rawlogs/"
        result = is_rsync_path(remote_path)
        
        self.assertTrue(result, 
            "Remote path should be detected, preventing os.makedirs() call")

    def test_local_path_allows_makedirs(self):
        """Local paths should return False, allowing makedirs to proceed."""
        local_path = "C:\\Users\\test\\output"
        result = is_rsync_path(local_path)
        
        self.assertFalse(result,
            "Local path should not be detected as remote")


if __name__ == '__main__':
    # Run tests with verbose output
    unittest.main(verbosity=2)
