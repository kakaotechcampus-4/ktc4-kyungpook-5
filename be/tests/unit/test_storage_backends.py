from types import SimpleNamespace
import sys

import pytest

from app.infra import storage


def test_local_upload_preserves_relative_key(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "get_settings", lambda: SimpleNamespace(storage_backend="local", storage_dir=str(tmp_path)))
    key = storage.save_file("club-1", "../minutes.csv", b"hello")
    assert key.startswith("club-1/") and key.endswith("_minutes.csv")
    assert (tmp_path / key).read_bytes() == b"hello"


def test_s3_upload_returns_key_only_after_put(monkeypatch):
    calls = []
    client = SimpleNamespace(put_object=lambda **kwargs: calls.append(kwargs))
    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=lambda service, region_name: client))
    monkeypatch.setattr(storage, "get_settings", lambda: SimpleNamespace(storage_backend="s3", s3_bucket="private", s3_region="ap-northeast-2"))
    key = storage.save_file("club-1", "minutes.csv", b"hello")
    assert key.startswith("s3:club-1/")
    assert calls == [{"Bucket": "private", "Key": key[3:], "Body": b"hello"}]


def test_s3_upload_failure_is_not_reported_as_success(monkeypatch):
    def fail(**kwargs):
        raise RuntimeError("upload failed")
    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=lambda service, region_name: SimpleNamespace(put_object=fail)))
    monkeypatch.setattr(storage, "get_settings", lambda: SimpleNamespace(storage_backend="s3", s3_bucket="private", s3_region="ap-northeast-2"))
    with pytest.raises(RuntimeError, match="upload failed"):
        storage.save_file("club-1", "minutes.csv", b"hello")


def test_s3_read_uses_saved_key(monkeypatch):
    from io import BytesIO
    calls = []
    def get_object(**kwargs):
        calls.append(kwargs)
        return {"Body": BytesIO(b"original")}
    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=lambda service, region_name: SimpleNamespace(get_object=get_object)))
    monkeypatch.setattr(storage, "get_settings", lambda: SimpleNamespace(s3_bucket="private", s3_region="ap-northeast-2"))
    assert storage.read_file("s3:club-1/file.csv") == b"original"
    assert calls == [{"Bucket": "private", "Key": "club-1/file.csv"}]


def test_local_read_blocks_escape(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "get_settings", lambda: SimpleNamespace(storage_dir=str(tmp_path)))
    with pytest.raises(ValueError):
        storage.read_file("../outside")


def test_download_checks_membership_before_read(monkeypatch):
    import asyncio
    from app.routers import records
    from app.core.exceptions import Forbidden

    async def record(*args, **kwargs):
        return SimpleNamespace(club_id="other-club", storage_key="s3:secret", file_name="a.csv")
    async def deny(*args, **kwargs):
        raise Forbidden()
    def must_not_read(*args):
        pytest.fail("storage read before authorization")
    monkeypatch.setattr(records.record_service, "get_record", record)
    monkeypatch.setattr(records, "ensure_member", deny)
    monkeypatch.setattr(records, "read_file", must_not_read)
    with pytest.raises(Forbidden):
        asyncio.run(records.download_record_file("rec", account=object(), session=object()))
