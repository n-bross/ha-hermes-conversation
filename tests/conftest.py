import pytest
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

@pytest.fixture
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

@pytest.fixture
def tmp_db(tmp_path):
    return tmp_path / "test_sessions.sqlite3"
