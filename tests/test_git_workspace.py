"""Tests for agent.services.git_workspace helpers."""

from __future__ import annotations

from pathlib import Path

from git import Actor, Repo

from agent.services.git_workspace import checkout_branch, normalize_git_url

TEST_ACTOR = Actor("Test User", "test@example.com")


def test_normalize_git_url_strips_credentials():
    url = "https://token@example.com:8443/foo/bar.git"
    assert normalize_git_url(url) == "https://example.com:8443/foo/bar.git"


def test_checkout_branch_switches_to_existing_branch(tmp_path):
    remote_dir = _setup_remote_repo(tmp_path)
    work_dir = tmp_path / "work"
    Repo.clone_from(remote_dir.as_posix(), work_dir)

    repo = Repo(work_dir)
    repo.git.checkout("-b", "feature/test")
    (Path(work_dir) / "README.md").write_text("feature", encoding="utf-8")
    repo.index.add(["README.md"])
    repo.index.commit("feat: add feature", author=TEST_ACTOR, committer=TEST_ACTOR)
    repo.remotes.origin.push("feature/test:feature/test")
    repo.git.checkout(repo.refs.master)

    checkout_branch(remote_dir.as_posix(), "feature/test", work_dir.as_posix())

    refreshed = Repo(work_dir)
    assert refreshed.active_branch.name == "feature/test"


def _setup_remote_repo(tmp_path) -> Path:
    remote_dir = tmp_path / "remote.git"
    Repo.init(remote_dir, bare=True)

    local_src = tmp_path / "src"
    src_repo = Repo.init(local_src)
    (local_src / "README.md").write_text("root", encoding="utf-8")
    src_repo.index.add(["README.md"])
    src_repo.index.commit("init", author=TEST_ACTOR, committer=TEST_ACTOR)
    origin = src_repo.create_remote("origin", remote_dir.as_posix())
    origin.push(src_repo.head.ref)
    return remote_dir
