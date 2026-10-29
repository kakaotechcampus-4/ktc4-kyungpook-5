"""업로드 파일 저장. 기존 로컬 키와 새 S3 키를 구분한다."""

import uuid
from pathlib import Path

from app.core.config import get_settings


def save_file(club_id: str, file_name: str, content: bytes) -> str:
    """저장에 성공한 경우에만 저장소 키를 반환한다."""
    settings = get_settings()
    safe_name = f"{uuid.uuid4().hex}_{Path(file_name).name}"
    relative = f"{club_id}/{safe_name}"
    if settings.storage_backend == "s3":
        if not settings.s3_bucket.strip():
            raise RuntimeError("S3_BUCKET is required when STORAGE_BACKEND=s3")
        import boto3

        boto3.client("s3", region_name=settings.s3_region).put_object(
            Bucket=settings.s3_bucket, Key=relative, Body=content
        )
        return f"s3:{relative}"
    if settings.storage_backend != "local":
        raise RuntimeError("Unsupported STORAGE_BACKEND")
    full_path = Path(settings.storage_dir) / relative
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_bytes(content)
    return relative
