"""Integration tests for repository management helpers."""

from __future__ import annotations

from pathlib import Path

from agent.services.git_workspace import ensure_repository_exists
from git import Actor, Repo

TEST_ACTOR = Actor("Integration User", "integration@example.com")


def test_ensure_repository_exists_clones_remote_repo(tmp_path):
    remote_dir = _setup_remote_repo(tmp_path / "remote")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    codespace = workspace / "code"
    codespace.mkdir()

    ensure_repository_exists(remote_dir.as_posix(), codespace.as_posix())

    repo = Repo(codespace)
    assert repo.remotes.origin.url == remote_dir.as_posix()
    assert (codespace / "README.md").read_text(encoding="utf-8") == "root"


def test_ensure_repository_exists_reclones_when_remote_changes(tmp_path):
    primary_remote = _setup_remote_repo(tmp_path / "remote_primary")
    fallback_remote = _setup_remote_repo(tmp_path / "remote_fallback", contents="alt")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    codespace = workspace / "code"
    codespace.mkdir()

    ensure_repository_exists(primary_remote.as_posix(), codespace.as_posix())

    repo = Repo(codespace)
    assert repo.remotes.origin.url == primary_remote.as_posix()
    assert (codespace / "README.md").read_text(encoding="utf-8") == "root"

    ensure_repository_exists(fallback_remote.as_posix(), codespace.as_posix())

    refreshed = Repo(codespace)
    assert refreshed.remotes.origin.url == fallback_remote.as_posix()
    assert (codespace / "README.md").read_text(encoding="utf-8") == "alt"


def _setup_remote_repo(path: Path, contents: str = "root") -> Path:
    remote_dir = path
    Repo.init(remote_dir, bare=True)

    local_src = path.parent / f"src_{path.name}"
    src_repo = Repo.init(local_src)
    (local_src / "README.md").write_text(contents, encoding="utf-8")
    src_repo.index.add(["README.md"])
    src_repo.index.commit("init", author=TEST_ACTOR, committer=TEST_ACTOR)
    origin = src_repo.create_remote("origin", remote_dir.as_posix())
    origin.push(src_repo.head.ref)
    return remote_dir
