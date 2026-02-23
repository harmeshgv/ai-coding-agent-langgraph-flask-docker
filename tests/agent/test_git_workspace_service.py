"""Tests for git workspace service functionality."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from git.exc import GitCommandError


class TestCheckoutBranch:
    """Tests for checkout_branch function."""

    def test_checkout_existing_local_branch(self, monkeypatch):
        """Should checkout existing local branch."""
        from app.agent.services.git_workspace import checkout_branch
        
        # Setup mocks
        mock_isdir = MagicMock(return_value=True)
        mock_repo_class = MagicMock()
        mock_repo = MagicMock()
        mock_repo.heads = ["main", "feature-branch"]
        mock_repo_class.return_value = mock_repo
        
        # Apply patches
        monkeypatch.setattr("app.agent.services.git_workspace.os.path.isdir", mock_isdir)
        monkeypatch.setattr("app.agent.services.git_workspace.Repo", mock_repo_class)
        
        # Execute
        checkout_branch("https://github.com/test/repo.git", "feature-branch", "/tmp/test")
        
        # Verify
        mock_isdir.assert_called_once_with("/tmp/test/.git")
        mock_repo.git.checkout.assert_called_once_with("feature-branch")

    def test_checkout_remote_branch_success(self, monkeypatch):
        """Should checkout remote branch when fetch succeeds."""
        from app.agent.services.git_workspace import checkout_branch
        
        # Setup mocks
        mock_isdir = MagicMock(return_value=True)
        mock_repo_class = MagicMock()
        mock_repo = MagicMock()
        mock_repo.heads = ["main"]
        mock_repo.remotes.origin.fetch.return_value = None
        mock_repo.refs = {"origin/feature-branch": "remote_ref"}
        mock_repo_class.return_value = mock_repo
        
        # Apply patches
        monkeypatch.setattr("app.agent.services.git_workspace.os.path.isdir", mock_isdir)
        monkeypatch.setattr("app.agent.services.git_workspace.Repo", mock_repo_class)
        
        # Execute
        checkout_branch("https://github.com/test/repo.git", "feature-branch", "/tmp/test")
        
        # Verify
        mock_isdir.assert_called_once_with("/tmp/test/.git")
        mock_repo.remotes.origin.fetch.assert_called_once_with("feature-branch")
        mock_repo.git.checkout.assert_called_once_with("-b", "feature-branch", "origin/feature-branch")

    def test_create_local_branch_when_remote_not_found(self, monkeypatch):
        """Should create local branch when remote fetch fails."""
        from app.agent.services.git_workspace import checkout_branch
        
        # Setup mocks
        mock_isdir = MagicMock(return_value=True)
        mock_repo_class = MagicMock()
        mock_repo = MagicMock()
        # Start with only main branch, not feature-branch
        mock_repo.heads = ["main"]
        mock_repo.remotes.origin.fetch.side_effect = GitCommandError("Remote not found")
        # After checkout, simulate branch creation by updating heads
        def checkout_side_effect(*args, **kwargs):
            if args[0] == "-b" and args[1] == "feature-branch":
                mock_repo.heads.append("feature-branch")
        mock_repo.git.checkout.side_effect = checkout_side_effect
        mock_repo_class.return_value = mock_repo
        
        # Apply patches
        monkeypatch.setattr("app.agent.services.git_workspace.os.path.isdir", mock_isdir)
        monkeypatch.setattr("app.agent.services.git_workspace.Repo", mock_repo_class)
        
        # Execute
        checkout_branch("https://github.com/test/repo.git", "feature-branch", "/tmp/test")
        
        # Verify
        mock_isdir.assert_called_once_with("/tmp/test/.git")
        mock_repo.remotes.origin.fetch.assert_called_once_with("feature-branch")
        mock_repo.git.checkout.assert_called_once_with("-b", "feature-branch")

    def test_create_local_branch_verification_failure(self, monkeypatch):
        """Should raise error when branch creation verification fails."""
        from app.agent.services.git_workspace import checkout_branch
        
        # Setup mocks
        mock_isdir = MagicMock(return_value=True)
        mock_repo_class = MagicMock()
        mock_repo = MagicMock()
        mock_repo.heads = ["main"]  # Branch not created successfully
        mock_repo.remotes.origin.fetch.side_effect = GitCommandError("Remote not found")
        mock_repo.git.checkout.side_effect = GitCommandError("Checkout failed")
        mock_repo_class.return_value = mock_repo
        
        # Apply patches
        monkeypatch.setattr("app.agent.services.git_workspace.os.path.isdir", mock_isdir)
        monkeypatch.setattr("app.agent.services.git_workspace.Repo", mock_repo_class)
        
        # Execute & Verify
        with pytest.raises(GitCommandError):
            checkout_branch("https://github.com/test/repo.git", "feature-branch", "/tmp/test")

    def test_create_local_branch_when_remote_ref_not_found(self, monkeypatch):
        """Should create local branch when remote ref doesn't exist after fetch."""
        from app.agent.services.git_workspace import checkout_branch
        
        # Setup mocks
        mock_isdir = MagicMock(return_value=True)
        mock_repo_class = MagicMock()
        mock_repo = MagicMock()
        mock_repo.heads = ["main"]
        mock_repo.remotes.origin.fetch.return_value = None
        mock_repo.refs = {}  # No remote ref found
        # After checkout, simulate branch creation by updating heads
        def checkout_side_effect(*args, **kwargs):
            if args[0] == "-b" and args[1] == "feature-branch":
                mock_repo.heads.append("feature-branch")
        mock_repo.git.checkout.side_effect = checkout_side_effect
        mock_repo_class.return_value = mock_repo
        
        # Apply patches
        monkeypatch.setattr("app.agent.services.git_workspace.os.path.isdir", mock_isdir)
        monkeypatch.setattr("app.agent.services.git_workspace.Repo", mock_repo_class)
        
        # Execute
        checkout_branch("https://github.com/test/repo.git", "feature-branch", "/tmp/test")
        
        # Verify
        mock_isdir.assert_called_once_with("/tmp/test/.git")
        mock_repo.remotes.origin.fetch.assert_called_once_with("feature-branch")
        mock_repo.git.checkout.assert_called_with("-b", "feature-branch")

    def test_exception_chaining_preserved(self, monkeypatch):
        """Should preserve exception chaining when GitCommandError occurs."""
        from app.agent.services.git_workspace import checkout_branch
        
        # Setup mocks
        mock_isdir = MagicMock(return_value=True)
        mock_logger = MagicMock()
        mock_repo_class = MagicMock()
        mock_repo = MagicMock()
        mock_repo.heads = ["main"]
        original_error = GitCommandError("Remote not found")
        mock_repo.remotes.origin.fetch.side_effect = original_error
        mock_repo.git.checkout.side_effect = GitCommandError("Checkout failed")
        mock_repo_class.return_value = mock_repo
        
        # Apply patches
        monkeypatch.setattr("app.agent.services.git_workspace.os.path.isdir", mock_isdir)
        monkeypatch.setattr("app.agent.services.git_workspace.logger", mock_logger)
        monkeypatch.setattr("app.agent.services.git_workspace.Repo", mock_repo_class)
        
        # Execute & Verify
        with pytest.raises(GitCommandError) as exc_info:
            checkout_branch("https://github.com/test/repo.git", "feature-branch", "/tmp/test")
        
        # Verify exception chaining
        assert exc_info.value.__cause__ is original_error
