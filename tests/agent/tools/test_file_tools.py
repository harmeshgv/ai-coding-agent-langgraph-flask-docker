"""Unit tests for file_tools.py"""

from unittest.mock import patch, mock_open

from app.agent.tools.file_tools import (
    _get_full_path,
    _get_full_workspace_path,
    _get_full_instance_path,
    write_to_file_in_workspace,
    write_to_file_in_instance_dir,
    read_file_in_workspace,
    read_file,
    list_files,
    write_to_file,
)


class TestGetFullPath:
    """Tests for _get_full_path function"""

    def test_get_full_path_normal(self):
        """Test normal path construction"""
        with patch("os.path.realpath") as mock_realpath:
            mock_realpath.side_effect = lambda x: x
            result = _get_full_path("/workspace", "test.txt")
            assert result == "/workspace/test.txt"

    def test_get_full_path_strips_leading_slash(self):
        """Test that leading slashes are stripped"""
        with patch("os.path.realpath") as mock_realpath:
            mock_realpath.side_effect = lambda x: x
            result = _get_full_path("/workspace", "/test.txt")
            assert result == "/workspace/test.txt"

    def test_get_full_path_access_denied(self):
        """Test access denied when path is outside base"""
        with patch("os.path.realpath") as mock_realpath:
            # Simulate realpath resolving .. to go outside workspace
            def realpath_side_effect(path):
                if "outside" in path:
                    return "/outside.txt"
                return path
            mock_realpath.side_effect = realpath_side_effect
            result = _get_full_path("/workspace", "../outside.txt")
            assert "Access denied" in result


class TestGetFullWorkspacePath:
    """Tests for _get_full_workspace_path function"""

    @patch("app.agent.tools.file_tools.get_workspace")
    def test_get_full_workspace_path(self, mock_get_workspace):
        """Test workspace path construction"""
        mock_get_workspace.return_value = "/workspace"
        with patch("os.path.realpath") as mock_realpath:
            mock_realpath.side_effect = lambda x: x
            result = _get_full_workspace_path("test.txt")
            assert result == "/workspace/test.txt"


class TestGetFullInstancePath:
    """Tests for _get_full_instance_path function"""

    @patch("app.agent.tools.file_tools.get_instance_dir")
    def test_get_full_instance_path(self, mock_get_instance_dir):
        """Test instance path construction"""
        mock_get_instance_dir.return_value = "/instance"
        with patch("os.path.realpath") as mock_realpath:
            mock_realpath.side_effect = lambda x: x
            result = _get_full_instance_path("test.txt")
            assert result == "/instance/test.txt"


class TestWriteToFileInWorkspace:
    """Tests for write_to_file_in_workspace function"""

    @patch("app.agent.tools.file_tools.get_workspace")
    @patch("builtins.open", new_callable=mock_open)
    @patch("os.makedirs")
    @patch("os.path.realpath")
    def test_write_to_file_success(self, mock_realpath, mock_makedirs, mock_file, mock_get_workspace):
        """Test successful file write"""
        mock_get_workspace.return_value = "/workspace"
        mock_realpath.side_effect = lambda x: x
        
        result = write_to_file_in_workspace("test.txt", "content")
        
        assert "Successfully wrote" in result
        mock_file.assert_called_once_with("/workspace/test.txt", "w", encoding="utf-8")
        mock_file().write.assert_called_once_with("content")

    @patch("app.agent.tools.file_tools.get_workspace")
    @patch("builtins.open", side_effect=IOError("Permission denied"))
    @patch("os.makedirs")
    @patch("os.path.realpath")
    def test_write_to_file_error(self, mock_realpath, mock_makedirs, mock_file, mock_get_workspace):
        """Test file write error handling"""
        mock_get_workspace.return_value = "/workspace"
        mock_realpath.side_effect = lambda x: x
        
        result = write_to_file_in_workspace("test.txt", "content")
        
        assert "ERROR writing file" in result


class TestWriteToFileInInstanceDir:
    """Tests for write_to_file_in_instance_dir function"""

    @patch("app.agent.tools.file_tools.get_instance_dir")
    @patch("builtins.open", new_callable=mock_open)
    @patch("os.makedirs")
    @patch("os.path.realpath")
    def test_write_to_instance_dir_success(self, mock_realpath, mock_makedirs, mock_file, mock_get_instance_dir):
        """Test successful file write to instance dir"""
        mock_get_instance_dir.return_value = "/instance"
        mock_realpath.side_effect = lambda x: x
        
        result = write_to_file_in_instance_dir("test.txt", "content")
        
        assert "Successfully wrote" in result
        mock_file.assert_called_once_with("/instance/test.txt", "w", encoding="utf-8")


class TestReadFileInWorkspace:
    """Tests for read_file_in_workspace function"""

    @patch("app.agent.tools.file_tools.get_workspace")
    @patch("builtins.open", new_callable=mock_open, read_data="file content")
    @patch("os.path.exists")
    @patch("os.path.realpath")
    def test_read_file_success(self, mock_realpath, mock_exists, mock_file, mock_get_workspace):
        """Test successful file read"""
        mock_get_workspace.return_value = "/workspace"
        mock_realpath.side_effect = lambda x: x
        mock_exists.return_value = True
        
        result = read_file_in_workspace("test.txt")
        
        assert result == "file content"
        mock_file.assert_called_once_with("/workspace/test.txt", "r", encoding="utf-8")

    @patch("app.agent.tools.file_tools.get_workspace")
    @patch("os.path.exists")
    @patch("os.path.realpath")
    def test_read_file_not_exists(self, mock_realpath, mock_exists, mock_get_workspace):
        """Test reading non-existent file"""
        mock_get_workspace.return_value = "/workspace"
        mock_realpath.side_effect = lambda x: x
        mock_exists.return_value = False
        
        result = read_file_in_workspace("test.txt")
        
        assert "ERROR: File" in result
        assert "does not exist" in result

    @patch("app.agent.tools.file_tools.get_workspace")
    @patch("builtins.open", new_callable=mock_open, read_data="")
    @patch("os.path.exists")
    @patch("os.path.realpath")
    def test_read_file_empty(self, mock_realpath, mock_exists, mock_file, mock_get_workspace):
        """Test reading empty file"""
        mock_get_workspace.return_value = "/workspace"
        mock_realpath.side_effect = lambda x: x
        mock_exists.return_value = True
        
        result = read_file_in_workspace("test.txt")
        
        assert result == "(File is empty)"


class TestReadFileTool:
    """Tests for read_file tool"""

    @patch("app.agent.tools.file_tools.read_file_in_workspace")
    def test_read_file_tool(self, mock_read):
        """Test read_file tool delegates to read_file_in_workspace"""
        mock_read.return_value = "content"
        
        result = read_file.invoke({"filepath": "test.txt"})
        
        assert result == "content"
        mock_read.assert_called_once_with("test.txt")


class TestListFiles:
    """Tests for list_files function"""

    @patch("app.agent.tools.file_tools.get_workspace")
    @patch("os.walk")
    @patch("os.path.realpath")
    def test_list_files_basic(self, mock_realpath, mock_walk, mock_get_workspace):
        """Test basic file listing"""
        mock_get_workspace.return_value = "/workspace"
        mock_realpath.side_effect = lambda x: x
        mock_walk.return_value = [
            ("/workspace", ["dir1"], ["file1.txt", "file2.py"]),
            ("/workspace/dir1", [], ["file3.java"]),
        ]
        
        result = list_files.invoke({"directory": "."})
        
        assert "file1.txt" in result
        assert "file2.py" in result
        assert "file3.java" in result

    @patch("app.agent.tools.file_tools.get_workspace")
    @patch("os.walk")
    @patch("os.path.realpath")
    def test_list_files_with_pattern(self, mock_realpath, mock_walk, mock_get_workspace):
        """Test file listing with pattern filter"""
        mock_get_workspace.return_value = "/workspace"
        mock_realpath.side_effect = lambda x: x
        mock_walk.return_value = [
            ("/workspace", [], ["file1.txt", "file2.py", "file3.java"]),
        ]
        
        result = list_files.invoke({"directory": ".", "pattern": "*.py"})
        
        assert "file2.py" in result
        assert "file1.txt" not in result
        assert "file3.java" not in result

    @patch("app.agent.tools.file_tools.get_workspace")
    @patch("os.walk")
    @patch("os.path.realpath")
    def test_list_files_max_files(self, mock_realpath, mock_walk, mock_get_workspace):
        """Test file listing with max_files limit"""
        mock_get_workspace.return_value = "/workspace"
        mock_realpath.side_effect = lambda x: x
        mock_walk.return_value = [
            ("/workspace", [], [f"file{i}.txt" for i in range(10)]),
        ]
        
        result = list_files.invoke({"directory": ".", "max_files": 5})
        
        assert "[TRUNCATED" in result
        assert result.count("\n") <= 7  # 5 files + truncation message

    @patch("app.agent.tools.file_tools.get_workspace")
    @patch("os.walk")
    @patch("os.path.realpath")
    def test_list_files_summary_mode(self, mock_realpath, mock_walk, mock_get_workspace):
        """Test file listing in summary mode"""
        mock_get_workspace.return_value = "/workspace"
        mock_realpath.side_effect = lambda x: x
        mock_walk.return_value = [
            ("/workspace", ["dir1"], ["file1.txt", "file2.py"]),
            ("/workspace/dir1", [], ["file3.java"]),
        ]
        
        result = list_files.invoke({"directory": ".", "summary": True})
        
        assert "Directory Summary:" in result
        assert "2 files" in result
        assert "1 files" in result

    @patch("app.agent.tools.file_tools.get_workspace")
    @patch("os.walk")
    @patch("os.path.realpath")
    def test_list_files_max_depth(self, mock_realpath, mock_walk, mock_get_workspace):
        """Test file listing with max_depth limit"""
        mock_get_workspace.return_value = "/workspace"
        mock_realpath.side_effect = lambda x: x
        
        def walk_generator(path):
            yield ("/workspace", ["dir1"], ["file1.txt"])
            yield ("/workspace/dir1", ["dir2"], ["file2.txt"])
            yield ("/workspace/dir1/dir2", [], ["file3.txt"])
        
        mock_walk.return_value = walk_generator("/workspace")
        
        result = list_files.invoke({"directory": ".", "max_depth": 1})
        
        assert "file1.txt" in result
        assert "file2.txt" in result
        assert "file3.txt" not in result

    @patch("app.agent.tools.file_tools.get_workspace")
    @patch("os.walk")
    @patch("os.path.realpath")
    def test_list_files_ignores_patterns(self, mock_realpath, mock_walk, mock_get_workspace):
        """Test that ignored directories are filtered out"""
        mock_get_workspace.return_value = "/workspace"
        mock_realpath.side_effect = lambda x: x
        mock_walk.return_value = [
            ("/workspace", [".git", "node_modules", "src"], ["file1.txt"]),
            ("/workspace/src", [], ["file2.py"]),
        ]
        
        result = list_files.invoke({"directory": "."})
        
        assert "file1.txt" in result
        assert "file2.py" in result
        assert ".git" not in result
        assert "node_modules" not in result

    @patch("app.agent.tools.file_tools.get_workspace")
    @patch("os.walk")
    @patch("os.path.realpath")
    def test_list_files_no_files(self, mock_realpath, mock_walk, mock_get_workspace):
        """Test listing when no files found"""
        mock_get_workspace.return_value = "/workspace"
        mock_realpath.side_effect = lambda x: x
        mock_walk.return_value = [
            ("/workspace", [], []),
        ]
        
        result = list_files.invoke({"directory": "."})
        
        assert result == "No files found."

    @patch("app.agent.tools.file_tools.get_workspace")
    @patch("os.path.realpath")
    def test_list_files_access_denied(self, mock_realpath, mock_get_workspace):
        """Test access denied for paths outside workspace"""
        mock_get_workspace.return_value = "/workspace"
        # Simulate realpath resolving paths outside workspace
        def realpath_side_effect(path):
            if "/workspace" in path and "outside" not in path:
                return path
            elif "outside" in path:
                return "/outside"
            return "/workspace"
        mock_realpath.side_effect = realpath_side_effect
        
        result = list_files.invoke({"directory": "../outside"})
        
        assert result == "Access denied"


class TestWriteToFileTool:
    """Tests for write_to_file tool"""

    @patch("app.agent.tools.file_tools.write_to_file_in_workspace")
    def test_write_to_file_tool(self, mock_write):
        """Test write_to_file tool delegates to write_to_file_in_workspace"""
        mock_write.return_value = "Successfully wrote to /workspace/test.txt"
        
        result = write_to_file.invoke({"filepath": "test.txt", "content": "content"})
        
        assert "Successfully wrote" in result
        mock_write.assert_called_once_with("test.txt", "content")
