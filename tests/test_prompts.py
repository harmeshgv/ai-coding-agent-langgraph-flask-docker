"""Tests for agent.services.prompts."""

from __future__ import annotations

from agent.services.prompts import load_system_prompt


def test_load_system_prompt_reads_file(tmp_path, monkeypatch):
    workbench_dir = tmp_path / "workbench" / "backend"
    workbench_dir.mkdir(parents=True)
    prompt_file = workbench_dir / "systemprompt_coder.md"
    prompt_file.write_text("Hello from prompt", encoding="utf-8")

    monkeypatch.chdir(tmp_path)

    content = load_system_prompt("backend", "coder")

    assert content == "Hello from prompt"


def test_load_system_prompt_missing_file_returns_default(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    content = load_system_prompt("backend", "coder")

    assert content == "You are a helpful coding assistent."
