"""Integration tests for agent.runtime.prepare_runtime."""

from __future__ import annotations

from flask import Flask

from app.agent import runtime as runtime_module
from app.agent.runtime import AgentRuntimeContext, prepare_runtime
from app.core.extensions import db
from app.core.models import AgentConfig


def _create_app(database_uri: str) -> Flask:
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = database_uri
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)
    return app


def test_prepare_runtime_returns_context(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    codespace = workspace / "code"
    codespace.mkdir()
    monkeypatch.setenv("WORKSPACE", workspace.as_posix())
    monkeypatch.setenv("WORKBENCH", "workbench-backend")

    app = _create_app(f"sqlite:///{tmp_path / 'runtime.db'}")
    ensure_called = {}

    def fake_ensure(repo_url: str, work_dir: str):
        ensure_called["repo_url"] = repo_url
        ensure_called["work_dir"] = work_dir

    monkeypatch.setattr("app.agent.runtime.ensure_repository_exists", fake_ensure)

    with app.app_context():
        db.create_all()
        config = AgentConfig(
            task_system_type="TRELLO",
            github_repo_url="https://example.com/foo/bar.git",
            is_active=True,
            system_config={
                "env": {"FOO": "BAR"},
                "trello_readfrom_list": "todo",
            },
        )
        db.session.add(config)
        db.session.commit()

        context = prepare_runtime()

    assert isinstance(context, AgentRuntimeContext)
    assert context.agent_stack == "backend"
    assert context.agent_config.system_config["trello_readfrom_list"] == "todo"
    assert context.task_env["FOO"] == "BAR"
    assert "command" in context.system_def
    assert ensure_called["repo_url"] == "https://example.com/foo/bar.git"
    assert ensure_called["work_dir"] == codespace.as_posix()


def test_prepare_runtime_uses_default_repo_when_missing(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    codespace = workspace / "code"
    codespace.mkdir()
    monkeypatch.setenv("WORKSPACE", workspace.as_posix())
    monkeypatch.setenv("WORKBENCH", "workbench-frontend")

    app = _create_app(f"sqlite:///{tmp_path / 'runtime_default.db'}")

    captured = {}
    monkeypatch.setattr(
        runtime_module,
        "ensure_repository_exists",
        lambda repo_url, work_dir: captured.update(
            {"repo_url": repo_url, "work_dir": work_dir}
        ),
    )

    with app.app_context():
        db.create_all()
        config = AgentConfig(
            task_system_type="TRELLO",
            github_repo_url=None,
            is_active=True,
            system_config={"trello_readfrom_list": "todo", "env": {"FOO": "BAR"}},
        )
        db.session.add(config)
        db.session.commit()

        context = prepare_runtime()

    assert isinstance(context, AgentRuntimeContext)
    assert context.agent_stack == "frontend"
    # DEFAULT_REPO lives in runtime module
    expected_repo = config.github_repo_url
    assert captured["repo_url"] == expected_repo
    assert captured["work_dir"] == codespace.as_posix()
    assert context.agent_config.system_config == {
        "trello_readfrom_list": "todo",
        "env": {"FOO": "BAR"},
        "github_repo_url": expected_repo,
    }


def test_prepare_runtime_returns_none_for_unknown_system(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    codespace = workspace / "code"
    codespace.mkdir()
    monkeypatch.setenv("WORKSPACE", workspace.as_posix())
    monkeypatch.setenv("WORKBENCH", "workbench-backend")

    app = _create_app(f"sqlite:///{tmp_path / 'runtime_invalid.db'}")

    with app.app_context():
        db.create_all()
        config = AgentConfig(
            task_system_type="UNKNOWN",
            github_repo_url="https://example.com/foo/bar.git",
            is_active=True,
            system_config={},
        )
        db.session.add(config)
        db.session.commit()

        context = prepare_runtime()

    assert context is None
