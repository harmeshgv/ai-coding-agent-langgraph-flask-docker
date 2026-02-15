"""Integration tests for agent.runtime.prepare_runtime."""

from __future__ import annotations

from flask import Flask

from app.agent.runtime import RuntimeSetting, prepare_runtime
from app.core.extensions import db
from app.core.localdb.models import AgentSettings


def _create_app(database_uri: str) -> Flask:
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = database_uri
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)
    return app


def test_prepare_runtime_returns_context(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
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
        settings = AgentSettings(
            task_system_type="TRELLO",
            github_repo_url="https://example.com/foo/bar.git",
            is_active=True,
            task_readfrom_state="todo",
            llm_provider="ollama",
            llm_model_large="llama3",
            llm_model_small="llama3",
            llm_temperature="0.0",
        )
        db.session.add(settings)
        db.session.commit()

        context = prepare_runtime()

    assert isinstance(context, RuntimeSetting)
    assert context.agent_stack == "backend"
    assert context.agent_settings.task_readfrom_state == "todo"
    assert "command" in context.mcp_system_def
    assert ensure_called["repo_url"] == "https://example.com/foo/bar.git"
    assert ensure_called["work_dir"] == workspace.as_posix()


def test_prepare_runtime_returns_none_for_unknown_system(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("WORKSPACE", workspace.as_posix())
    monkeypatch.setenv("WORKBENCH", "workbench-backend")

    app = _create_app(f"sqlite:///{tmp_path / 'runtime_invalid.db'}")

    monkeypatch.setattr(
        "app.agent.runtime.ensure_repository_exists", lambda repo_url, work_dir: None
    )

    with app.app_context():
        db.create_all()
        settings = AgentSettings(
            task_system_type="UNKNOWN",
            github_repo_url="https://example.com/foo/bar.git",
            is_active=True,
            llm_provider="ollama",
            llm_model_large="llama3",
            llm_model_small="llama3",
            llm_temperature="0.0",
        )
        db.session.add(settings)
        db.session.commit()

        context = prepare_runtime()

    assert context is None
