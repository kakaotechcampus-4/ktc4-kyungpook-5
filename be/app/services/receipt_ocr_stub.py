"""영수증 이미지 → 지출 초안 추출의 더미 구현.

실제 AI 추출(이미지를 받는 채팅 모델 호출)은 #112가 명시한 대로 별도 이슈에서
AI가 맡는다. 이 함수는 그 자리를 표시해두는 더미이며, 같은 파일을 올리면
같은 결과를 내도록 파일 해시로 금액만 결정론적으로 바꾼다 — 실제 OCR이
나올 때 이 함수만 교체하면 호출부(services/accounting_service.py)는 그대로 쓴다.
"""

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass
class ExtractedRow:
    spent_at: datetime | None
    merchant: str | None
    amount: int | None
    description: str | None
    category: str | None
    raw_fields: dict[str, str]
    field_confidence: dict[str, float] = field(default_factory=dict)


def extract_receipt(file_bytes: bytes) -> list[ExtractedRow]:
    """영수증 한 장 = 초안 한 행. 더미이므로 항상 한 행만 반환한다."""
    digest = hashlib.sha256(file_bytes).hexdigest()
    # 더미 금액: 파일마다 달라 보이게 하되 실제 추출이 아님을 숨기지 않는다.
    amount = 10_000 + (int(digest[:6], 16) % 90_000)

    return [
        ExtractedRow(
            spent_at=datetime.now(UTC),
            merchant="(더미 추출) 가맹점명 확인 필요",
            amount=amount,
            description="실제 OCR 연동 전 더미 결과입니다 — 검수 후 고쳐주세요.",
            category=None,
            raw_fields={"source": "receipt_ocr_stub", "file_sha256": digest},
            field_confidence={"amount": 0.3, "merchant": 0.0},
        )
    ]
