"""업로드 파일 저장. S3 연동 전까지 로컬 디스크(settings.storage_dir)를 쓴다.

storage_key는 저장소 기준 상대경로라 나중에 S3로 바꿔도 호출부가 바뀌지 않는다.
"""

import uuid
from pathlib import Path

from app.core.config import get_settings


def save_file(club_id: str, file_name: str, content: bytes) -> str:
    """파일을 저장하고 storage_key(상대경로)를 돌려준다."""
    settings = get_settings()
    safe_name = f"{uuid.uuid4().hex}_{Path(file_name).name}"
    relative = f"{club_id}/{safe_name}"
    full_path = Path(settings.storage_dir) / relative
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_bytes(content)
    return relative
