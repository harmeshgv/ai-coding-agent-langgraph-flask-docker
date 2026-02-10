"""Tests for pull_request module."""

from unittest.mock import MagicMock, patch

import pytest
import requests

from app.agent.services.pull_request import (
    PullRequest,
    GitHubContext,
    get_latest_open_pr_for_branch,
    check_pr_exists_for_branch,
    create_or_update_pr,
    update_existing_pr,
    create_new_pr,
    build_github_context,
    get_github_repo_info,
    get_github_repo_info_with_branch,
)


@pytest.fixture
def mock_env_token(monkeypatch):
    """Set GITHUB_TOKEN in environment."""
    from app.core.config import set_env_settings
    
    monkeypatch.setenv("GITHUB_TOKEN", "test_token_123")
    set_env_settings(None)  # Reset to reload from new environment


@pytest.fixture
def mock_github_context():
    """Create a mock GitHubContext."""
    return GitHubContext(
        owner="test-owner",
        repo="test-repo",
        branch="feature/test-branch",
        headers={
            "Authorization": "token test_token_123",
            "Accept": "application/vnd.github.v3+json",
        },
    )


@pytest.fixture
def mock_pr_data():
    """Create mock PR data from GitHub API."""
    return {
        "number": 42,
        "title": "Test PR",
        "body": "Test description",
        "html_url": "https://github.com/test-owner/test-repo/pull/42",
        "state": "open",
        "head": {"ref": "feature/test-branch"},
        "base": {"ref": "main"},
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-02T00:00:00Z",
    }


class TestGetGitHubRepoInfo:
    """Tests for get_github_repo_info function."""

    @patch("app.agent.services.pull_request.get_remote_url")
    def test_get_github_repo_info_https(self, mock_remote_url):
        """Test parsing HTTPS GitHub URL."""
        mock_remote_url.return_value = "https://github.com/owner/repo.git"
        
        owner, repo = get_github_repo_info()
        
        assert owner == "owner"
        assert repo == "repo"

    @patch("app.agent.services.pull_request.get_remote_url")
    def test_get_github_repo_info_ssh(self, mock_remote_url):
        """Test parsing SSH GitHub URL."""
        mock_remote_url.return_value = "git@github.com:owner/repo.git"
        
        owner, repo = get_github_repo_info()
        
        assert owner == "owner"
        assert repo == "repo"

    @patch("app.agent.services.pull_request.get_remote_url")
    def test_get_github_repo_info_no_git_suffix(self, mock_remote_url):
        """Test parsing GitHub URL without .git suffix."""
        mock_remote_url.return_value = "https://github.com/owner/repo"
        
        owner, repo = get_github_repo_info()
        
        assert owner == "owner"
        assert repo == "repo"

    @patch("app.agent.services.pull_request.get_remote_url")
    def test_get_github_repo_info_invalid_url(self, mock_remote_url):
        """Test handling invalid URL."""
        mock_remote_url.return_value = "https://example.com/repo"
        
        owner, repo = get_github_repo_info()
        
        assert owner is None
        assert repo is None

    @patch("app.agent.services.pull_request.get_remote_url")
    def test_get_github_repo_info_no_remote(self, mock_remote_url):
        """Test handling missing remote."""
        mock_remote_url.return_value = None
        
        owner, repo = get_github_repo_info()
        
        assert owner is None
        assert repo is None


class TestGetGitHubRepoInfoWithBranch:
    """Tests for get_github_repo_info_with_branch function."""

    @patch("app.agent.services.pull_request.get_current_branch")
    @patch("app.agent.services.pull_request.get_remote_url")
    def test_get_repo_info_with_branch_success(self, mock_remote_url, mock_branch):
        """Test successful retrieval of owner, repo, and branch."""
        mock_remote_url.return_value = "https://github.com/owner/repo.git"
        mock_branch.return_value = "feature/test"
        
        owner, repo, branch = get_github_repo_info_with_branch()
        
        assert owner == "owner"
        assert repo == "repo"
        assert branch == "feature/test"

    @patch("app.agent.services.pull_request.get_remote_url")
    def test_get_repo_info_with_branch_no_remote(self, mock_remote_url):
        """Test handling missing remote."""
        mock_remote_url.return_value = None
        
        owner, repo, branch = get_github_repo_info_with_branch()
        
        assert owner is None
        assert repo is None
        assert branch is None

    @patch("app.agent.services.pull_request.get_current_branch")
    @patch("app.agent.services.pull_request.get_remote_url")
    def test_get_repo_info_with_branch_no_branch(self, mock_remote_url, mock_branch):
        """Test handling missing branch."""
        mock_remote_url.return_value = "https://github.com/owner/repo.git"
        mock_branch.return_value = None
        
        owner, repo, branch = get_github_repo_info_with_branch()
        
        assert owner is None
        assert repo is None
        assert branch is None


class TestBuildGitHubContext:
    """Tests for build_github_context function."""

    @patch("app.agent.services.pull_request.get_github_repo_info_with_branch")
    def test_build_github_context_success(self, mock_get_info):
        """Test successful context building."""
        mock_get_info.return_value = ("owner", "repo", "feature/test")
        
        context = build_github_context("test_token")
        
        assert context is not None
        assert context.owner == "owner"
        assert context.repo == "repo"
        assert context.branch == "feature/test"
        assert context.headers["Authorization"] == "token test_token"

    @patch("app.agent.services.pull_request.get_github_repo_info_with_branch")
    def test_build_github_context_missing_info(self, mock_get_info):
        """Test handling missing repository info."""
        mock_get_info.return_value = (None, None, None)
        
        context = build_github_context("test_token")
        
        assert context is None


class TestGetLatestOpenPrForBranch:
    """Tests for get_latest_open_pr_for_branch function."""

    @patch("app.agent.services.pull_request.get_github_repo_info")
    @patch("requests.get")
    def test_get_latest_open_pr_success(
        self, mock_requests_get, mock_get_info, mock_env_token, mock_pr_data
    ):
        """Test successful PR retrieval."""
        mock_get_info.return_value = ("owner", "repo")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [mock_pr_data]
        mock_requests_get.return_value = mock_response
        
        pr = get_latest_open_pr_for_branch("feature/test")
        
        assert pr is not None
        assert isinstance(pr, PullRequest)
        assert pr.number == 42
        assert pr.title == "Test PR"
        assert pr.html_url == "https://github.com/test-owner/test-repo/pull/42"

    @patch("app.agent.services.pull_request.get_github_repo_info")
    @patch("requests.get")
    def test_get_latest_open_pr_no_prs(
        self, mock_requests_get, mock_get_info, mock_env_token
    ):
        """Test when no PRs exist for branch."""
        mock_get_info.return_value = ("owner", "repo")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_requests_get.return_value = mock_response
        
        pr = get_latest_open_pr_for_branch("feature/test")
        
        assert pr is None

    @patch("app.agent.services.pull_request.get_github_repo_info")
    def test_get_latest_open_pr_no_token(self, mock_get_info, monkeypatch):
        """Test handling missing GITHUB_TOKEN."""
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        
        pr = get_latest_open_pr_for_branch("feature/test")
        
        assert pr is None

    @patch("app.agent.services.pull_request.get_github_repo_info")
    def test_get_latest_open_pr_no_repo_info(self, mock_get_info, mock_env_token):
        """Test handling missing repository info."""
        mock_get_info.return_value = (None, None)
        
        pr = get_latest_open_pr_for_branch("feature/test")
        
        assert pr is None

    @patch("app.agent.services.pull_request.get_github_repo_info")
    @patch("requests.get")
    def test_get_latest_open_pr_api_error(
        self, mock_requests_get, mock_get_info, mock_env_token
    ):
        """Test handling API error."""
        mock_get_info.return_value = ("owner", "repo")
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "Not Found"
        mock_requests_get.return_value = mock_response
        
        pr = get_latest_open_pr_for_branch("feature/test")
        
        assert pr is None

    @patch("app.agent.services.pull_request.get_github_repo_info")
    @patch("requests.get")
    def test_get_latest_open_pr_exception(
        self, mock_requests_get, mock_get_info, mock_env_token
    ):
        """Test handling exception during API call."""
        mock_get_info.return_value = ("owner", "repo")
        mock_requests_get.side_effect = requests.RequestException("Network error")
        
        pr = get_latest_open_pr_for_branch("feature/test")
        
        assert pr is None


class TestCheckPrExistsForBranch:
    """Tests for check_pr_exists_for_branch function."""

    @patch("app.agent.services.pull_request.get_latest_open_pr_for_branch")
    def test_check_pr_exists_true(self, mock_get_pr):
        """Test when PR exists."""
        mock_get_pr.return_value = PullRequest(
            number=42,
            title="Test",
            body="",
            html_url="https://github.com/owner/repo/pull/42",
            state="open",
            head_branch="feature/test",
            base_branch="main",
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-02T00:00:00Z",
        )
        
        exists = check_pr_exists_for_branch("feature/test")
        
        assert exists is True

    @patch("app.agent.services.pull_request.get_latest_open_pr_for_branch")
    def test_check_pr_exists_false(self, mock_get_pr):
        """Test when PR does not exist."""
        mock_get_pr.return_value = None
        
        exists = check_pr_exists_for_branch("feature/test")
        
        assert exists is False


class TestUpdateExistingPr:
    """Tests for update_existing_pr function."""

    @patch("requests.post")
    def test_update_existing_pr_success(
        self, mock_requests_post, mock_github_context, mock_pr_data
    ):
        """Test successful PR update."""
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_requests_post.return_value = mock_response
        
        success, message, url = update_existing_pr(
            mock_github_context, mock_pr_data, "Update body"
        )
        
        assert success is True
        assert "SUCCESS" in message
        assert url == "https://github.com/test-owner/test-repo/pull/42"

    @patch("requests.post")
    def test_update_existing_pr_failure(
        self, mock_requests_post, mock_github_context, mock_pr_data
    ):
        """Test failed PR update."""
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_requests_post.return_value = mock_response
        
        success, message, url = update_existing_pr(
            mock_github_context, mock_pr_data, "Update body"
        )
        
        assert success is False
        assert "ERROR" in message


class TestCreateNewPr:
    """Tests for create_new_pr function."""

    @patch("requests.post")
    def test_create_new_pr_success(self, mock_requests_post, mock_github_context):
        """Test successful PR creation."""
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "html_url": "https://github.com/owner/repo/pull/42"
        }
        mock_requests_post.return_value = mock_response
        
        success, message, url = create_new_pr(
            mock_github_context, "Test PR", "Test body"
        )
        
        assert success is True
        assert "SUCCESS" in message
        assert url == "https://github.com/owner/repo/pull/42"

    @patch("requests.post")
    def test_create_new_pr_fallback_to_master(
        self, mock_requests_post, mock_github_context
    ):
        """Test fallback to master when main doesn't exist."""
        mock_response_422 = MagicMock()
        mock_response_422.status_code = 422
        
        mock_response_201 = MagicMock()
        mock_response_201.status_code = 201
        mock_response_201.json.return_value = {
            "html_url": "https://github.com/owner/repo/pull/42"
        }
        
        mock_requests_post.side_effect = [mock_response_422, mock_response_201]
        
        success, message, url = create_new_pr(
            mock_github_context, "Test PR", "Test body"
        )
        
        assert success is True
        assert mock_requests_post.call_count == 2

    @patch("requests.post")
    def test_create_new_pr_failure(self, mock_requests_post, mock_github_context):
        """Test failed PR creation."""
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.text = "Forbidden"
        mock_requests_post.return_value = mock_response
        
        success, message, url = create_new_pr(
            mock_github_context, "Test PR", "Test body"
        )
        
        assert success is False
        assert "ERROR" in message
        assert url is None


class TestCreateOrUpdatePr:
    """Tests for create_or_update_pr function."""

    @patch("app.agent.services.pull_request.build_github_context")
    @patch("requests.get")
    @patch("app.agent.services.pull_request.update_existing_pr")
    def test_create_or_update_pr_updates_existing(
        self,
        mock_update_pr,
        mock_requests_get,
        mock_build_context,
        mock_env_token,
        mock_github_context,
        mock_pr_data,
    ):
        """Test updating existing PR."""
        mock_build_context.return_value = mock_github_context
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [mock_pr_data]
        mock_requests_get.return_value = mock_response
        mock_update_pr.return_value = (True, "SUCCESS", "https://github.com/...")
        
        success, message, url = create_or_update_pr("Test PR", "Test body")
        
        assert success is True
        mock_update_pr.assert_called_once()

    @patch("app.agent.services.pull_request.build_github_context")
    @patch("requests.get")
    @patch("app.agent.services.pull_request.create_new_pr")
    def test_create_or_update_pr_creates_new(
        self,
        mock_create_pr,
        mock_requests_get,
        mock_build_context,
        mock_env_token,
        mock_github_context,
    ):
        """Test creating new PR when none exists."""
        mock_build_context.return_value = mock_github_context
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_requests_get.return_value = mock_response
        mock_create_pr.return_value = (True, "SUCCESS", "https://github.com/...")
        
        success, message, url = create_or_update_pr("Test PR", "Test body")
        
        assert success is True
        mock_create_pr.assert_called_once()

    @patch("app.agent.services.pull_request.build_github_context")
    def test_create_or_update_pr_no_token(self, mock_build_context, monkeypatch):
        """Test handling missing GITHUB_TOKEN."""
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        
        success, message, url = create_or_update_pr("Test PR", "Test body")
        
        assert success is False
        assert "GITHUB_TOKEN missing" in message

    @patch("app.agent.services.pull_request.build_github_context")
    def test_create_or_update_pr_no_context(
        self, mock_build_context, mock_env_token
    ):
        """Test handling missing GitHub context."""
        mock_build_context.return_value = None
        
        success, message, url = create_or_update_pr("Test PR", "Test body")
        
        assert success is False
        assert "Missing GitHub context" in message

    @patch("app.agent.services.pull_request.build_github_context")
    def test_create_or_update_pr_on_main_branch(
        self, mock_build_context, mock_env_token
    ):
        """Test preventing PR creation from main branch."""
        context = GitHubContext(
            owner="owner",
            repo="repo",
            branch="main",
            headers={"Authorization": "token test"},
        )
        mock_build_context.return_value = context
        
        success, message, url = create_or_update_pr("Test PR", "Test body")
        
        assert success is False
        assert "main/master" in message
