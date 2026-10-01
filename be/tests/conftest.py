"""테스트 공통 fixture."""

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> TestClient:
    """서버를 띄우지 않고 앱을 직접 호출한다."""
    return TestClient(app)
