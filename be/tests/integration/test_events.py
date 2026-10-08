"""행사 목록 API의 응답 계약 테스트 (이슈 #92).

M1·L1 카드가 읽는 장소·인원 필드의 키 이름을 고정한다.
"""

from fastapi.testclient import TestClient

EVENTS_URL = "/api/v1/events"


def test_행사마다_location과_headcount_키가_있다(client: TestClient) -> None:
    response = client.get(EVENTS_URL)

    assert response.status_code == 200
    events = response.json()["data"]
    assert events
    for event in events:
        assert "location" in event
        assert "headcount" in event


def test_인원은_컬럼명이_아닌_headcount로_나간다(client: TestClient) -> None:
    """FE 명세 v1이 expectedHeadcount를 headcount로 통일했다."""
    response = client.get(EVENTS_URL)

    for event in response.json()["data"]:
        assert "expectedHeadcount" not in event
