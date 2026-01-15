"""Integration tests for agent.runtime.prepare_runtime."""

from __future__ import annotations

import json

from agent import runtime as runtime_module
from agent.runtime import AgentRuntimeContext, prepare_runtime
from core.extensions import db
from core.models import AgentConfig
from cryptography.fernet import Fernet
from flask import Flask


def _create_app(database_uri: str) -> Flask:
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = database_uri
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)
    return app


def _encrypt_config(key: Fernet, payload: dict) -> str:
    return key.encrypt(json.dumps(payload).encode()).decode()


def test_prepare_runtime_returns_context(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("WORKSPACE", workspace.as_posix())
    monkeypatch.setenv("WORKBENCH", "workbench-backend")

    app = _create_app(f"sqlite:///{tmp_path / 'runtime.db'}")
    encryption_key = Fernet(Fernet.generate_key())

    ensure_called = {}

    def fake_ensure(repo_url: str, work_dir: str):
        ensure_called["repo_url"] = repo_url
        ensure_called["work_dir"] = work_dir

    monkeypatch.setattr("agent.runtime.ensure_repository_exists", fake_ensure)

    with app.app_context():
        db.create_all()
        config = AgentConfig(
            task_system_type="TRELLO",
            github_repo_url="https://example.com/foo/bar.git",
            is_active=True,
            system_config_json=_encrypt_config(
                encryption_key,
                {
                    "env": {"FOO": "BAR"},
                    "trello_readfrom_list": "todo",
                },
            ),
        )
        db.session.add(config)
        db.session.commit()

        context = prepare_runtime(encryption_key)

    assert isinstance(context, AgentRuntimeContext)
    assert context.agent_stack == "backend"
    assert context.sys_config["trello_readfrom_list"] == "todo"
    assert context.task_env["FOO"] == "BAR"
    assert "command" in context.system_def
    assert ensure_called["repo_url"] == "https://example.com/foo/bar.git"
    assert ensure_called["work_dir"] == workspace.as_posix()


def test_prepare_runtime_uses_default_repo_when_missing(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("WORKSPACE", workspace.as_posix())
    monkeypatch.setenv("WORKBENCH", "workbench-frontend")

    app = _create_app(f"sqlite:///{tmp_path / 'runtime_default.db'}")
    encryption_key = Fernet(Fernet.generate_key())

    captured = {}
    monkeypatch.setattr(
        runtime_module,
        "ensure_repository_exists",
        lambda repo_url, work_dir: captured.update(
            {"repo_url": repo_url, "work_dir": work_dir}
        ),
    )

    sys_config_result = {}

    original_get_sys_config = runtime_module._get_sys_config

    def tracking_get_sys_config(config, key):
        result = original_get_sys_config(config, key)
        sys_config_result["value"] = result
        return result

    monkeypatch.setattr(runtime_module, "_get_sys_config", tracking_get_sys_config)

    with app.app_context():
        db.create_all()
        config = AgentConfig(
            task_system_type="TRELLO",
            github_repo_url=None,
            is_active=True,
            system_config_json=_encrypt_config(
                encryption_key,
                {"trello_readfrom_list": "todo", "env": {"FOO": "BAR"}},
            ),
        )
        db.session.add(config)
        db.session.commit()

        context = prepare_runtime(encryption_key)

    assert isinstance(context, AgentRuntimeContext)
    assert context.agent_stack == "frontend"
    # DEFAULT_REPO lives in runtime module
    expected_repo = config.github_repo_url or runtime_module.DEFAULT_REPO
    assert captured["repo_url"] == expected_repo
    assert captured["work_dir"] == workspace.as_posix()
    assert sys_config_result["value"] == {
        "trello_readfrom_list": "todo",
        "env": {"FOO": "BAR"},
        "github_repo_url": expected_repo,
    }


def test_prepare_runtime_returns_none_for_unknown_system(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("WORKSPACE", workspace.as_posix())
    monkeypatch.setenv("WORKBENCH", "workbench-backend")

    app = _create_app(f"sqlite:///{tmp_path / 'runtime_invalid.db'}")
    encryption_key = Fernet(Fernet.generate_key())

    # Still patch ensure_repository_exists to avoid network work
    monkeypatch.setattr(
        "agent.runtime.ensure_repository_exists", lambda *args, **kwargs: None
    )

    with app.app_context():
        db.create_all()
        config = AgentConfig(
            task_system_type="UNKNOWN",
            github_repo_url="https://example.com/foo/bar.git",
            is_active=True,
            system_config_json=_encrypt_config(encryption_key, {}),
        )
        db.session.add(config)
        db.session.commit()

        context = prepare_runtime(encryption_key)

    assert context is None
