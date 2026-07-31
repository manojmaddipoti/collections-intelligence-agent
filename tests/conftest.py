"""Shared deterministic database fixtures for MCP tests."""

from pathlib import Path

import pytest

from mcp_server import server
from scripts import seed_data


@pytest.fixture()
def seeded_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Build an isolated deterministic SQLite database for one test."""
    db_path = tmp_path / "ar_finance.db"
    monkeypatch.setattr(seed_data, "DB_PATH", db_path)
    monkeypatch.setattr(server, "DB_PATH", db_path)
    monkeypatch.delenv("DRAFT_DATABASE_URL", raising=False)
    monkeypatch.delenv("APPROVER_CREDENTIALS_JSON", raising=False)
    seed_data.main()
    return db_path
