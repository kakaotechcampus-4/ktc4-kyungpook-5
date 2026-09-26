"""승인 대기 Action 목록 API의 응답 계약 테스트 (이슈 #33).

값 자체가 아니라 FE가 의존하는 형태 — 봉투, 키 표기, enum 직렬화, 에러 형식 —
를 고정한다. mock 데이터가 바뀌어도 계약이 그대로면 통과해야 한다.
"""

from fastapi.testclient import TestClient

from app.services.event_service import MOCK_EVENT_ID

ACTIONS_URL = f"/api/v1/events/{MOCK_EVENT_ID}/actions"


def _walk_keys(value: object):
    """응답 전체에서 dict 키를 모은다. 중첩된 객체·배열도 본다."""
    if isinstance(value, dict):
        for key, child in value.items():
            yield key
            yield from _walk_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_keys(child)


def test_응답이_data_meta_봉투다(client: TestClient) -> None:
    response = client.get(ACTIONS_URL)

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"data", "meta"}
    assert isinstance(body["data"], list)
    assert set(body["meta"]) == {"page", "size", "totalCount"}


def test_응답_키에_snake_case가_없다(client: TestClient) -> None:
    response = client.get(ACTIONS_URL)

    snake_keys = sorted({key for key in _walk_keys(response.json()) if "_" in key})
    assert snake_keys == []


def test_status가_문자열_코드로_나간다(client: TestClient) -> None:
    response = client.get(ACTIONS_URL, params={"status": "PENDING"})

    statuses = [action["status"] for action in response.json()["data"]]
    assert statuses
    assert all(status == "PENDING" for status in statuses)
    assert all(isinstance(status, str) for status in statuses)


def test_없는_eventId는_404_에러_봉투다(client: TestClient) -> None:
    response = client.get("/api/v1/events/evt_없는행사/actions")

    assert response.status_code == 404
    body = response.json()
    assert set(body) == {"error"}
    assert body["error"]["code"] == "EVENT_NOT_FOUND"
    assert "detail" not in body


def test_잘못된_쿼리는_422_에러_봉투로_바뀐다(client: TestClient) -> None:
    response = client.get(ACTIONS_URL, params={"size": 0})

    assert response.status_code == 422
    body = response.json()
    assert set(body) == {"error"}
    assert body["error"]["code"] == "VALIDATION_FAILED"
    assert "size" in body["error"]["fields"]
    assert "detail" not in body
