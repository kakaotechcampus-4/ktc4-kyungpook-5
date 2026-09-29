"""라우터 공통 의존성."""

# 인증 도입 전까지 모든 요청을 시드 회원(alembic 시드 리비전)이 보낸 것으로 본다 (#63).
SEED_MEMBER_ID = "mbr_3a71c0"


def get_current_member_id() -> str:
    return SEED_MEMBER_ID
