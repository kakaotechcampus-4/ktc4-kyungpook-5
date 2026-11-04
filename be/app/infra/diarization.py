"""pyannoteAI batch diarization. Submission and polling are separate for recovery.

The service persists the provider job ID before polling; reconnects must not
resubmit paid work. No API key, signed URL, or provider response is logged.
"""

import asyncio
import math
import uuid
from pathlib import Path
from urllib.parse import quote, urlsplit

import httpx


class DiarizationError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code, self.message = code, message


class PyannoteDiarization:
    def __init__(self, api_key: str, model: str = 'precision-3', timeout_seconds: float = 60,
                 *, transport: httpx.AsyncBaseTransport | None = None):
        if not api_key.strip():
            raise DiarizationError('DIARIZATION_NOT_CONFIGURED', '화자분리 서비스 설정이 필요합니다.')
        if not model.strip() or timeout_seconds <= 0:
            raise DiarizationError('DIARIZATION_NOT_CONFIGURED', '화자분리 서비스 설정이 올바르지 않습니다.')
        self.api_key, self.model, self.timeout = api_key, model, timeout_seconds
        self.transport = transport

    async def _request(self, method: str, path: str, **kwargs) -> dict:
        try:
            async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as client:
                response = await client.request(method, 'https://api.pyannote.ai/v1/' + path,
                    headers={'Authorization': f'Bearer {self.api_key}'}, **kwargs)
                response.raise_for_status()
                result = response.json()
                if not isinstance(result, dict):
                    raise ValueError('Expected object')
                return result
        except httpx.TimeoutException as exc:
            raise DiarizationError('DIARIZATION_TIMEOUT', '화자분리 서비스의 응답을 확인하지 못했습니다.') from exc
        except httpx.HTTPError as exc:
            raise DiarizationError('DIARIZATION_PROVIDER_ERROR', '화자분리 서비스 요청에 실패했습니다.') from exc
        except (ValueError, TypeError) as exc:
            raise DiarizationError('DIARIZATION_INVALID_RESPONSE', '화자분리 응답을 읽지 못했습니다.') from exc

    async def submit(self, wav_path: Path) -> str:
        media = 'media://meetings/' + uuid.uuid4().hex + '.wav'
        result = await self._request('POST', 'media/input', json={'url': media})
        upload_url = result.get('url')
        try:
            parsed = urlsplit(upload_url) if isinstance(upload_url, str) else None
            valid_upload = (parsed is not None and parsed.scheme == 'https'
                            and bool(parsed.hostname) and parsed.username is None)
        except ValueError:
            valid_upload = False
        if not valid_upload:
            raise DiarizationError('DIARIZATION_INVALID_RESPONSE', '음성 업로드 주소를 확인하지 못했습니다.')

        async def chunks():
            with wav_path.open('rb') as source:
                while block := await asyncio.to_thread(source.read, 65536):
                    yield block
        try:
            # The upload host gets only audio, never the provider's bearer key.
            async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as client:
                response = await client.put(upload_url, content=chunks(), headers={
                    'Content-Type': 'application/octet-stream', 'Content-Length': str(wav_path.stat().st_size)})
                response.raise_for_status()
        except (OSError, httpx.HTTPError) as exc:
            raise DiarizationError('DIARIZATION_UPLOAD_FAILED', '화자분리용 음성을 업로드하지 못했습니다.') from exc
        result = await self._request('POST', 'diarize', json={'url': media, 'model': self.model})
        job_id = result.get('jobId')
        if not isinstance(job_id, str) or not job_id or len(job_id) > 200:
            raise DiarizationError('DIARIZATION_INVALID_RESPONSE', '화자분리 작업 번호를 확인하지 못했습니다.')
        return job_id

    async def result(self, job_id: str, *, duration_ms: int) -> list[dict] | None:
        if (not isinstance(job_id, str) or not job_id or len(job_id) > 200
                or type(duration_ms) is not int or duration_ms <= 0):
            raise DiarizationError('DIARIZATION_INVALID_RESPONSE', '화자분리 작업 정보를 확인하지 못했습니다.')
        payload = await self._request('GET', 'jobs/' + quote(job_id, safe=''))
        status = payload.get('status')
        if status in ('pending', 'created', 'running'):
            if payload.get('jobId') not in (None, job_id):
                raise DiarizationError('DIARIZATION_INVALID_RESPONSE', '화자분리 작업 정보를 확인하지 못했습니다.')
            return None
        if status in ('failed', 'canceled'):
            raise DiarizationError('DIARIZATION_FAILED', '화자분리에 실패했습니다. 원래 전사는 유지됩니다.')
        try:
            if status != 'succeeded' or payload.get('jobId') != job_id:
                raise ValueError('Unexpected job status')
            rows = payload['output']['diarization']
            if not isinstance(rows, list) or len(rows) > 100000:
                raise ValueError('Invalid turns')
            turns = []
            for row in rows:
                start, end, speaker = row['start'], row['end'], row['speaker']
                if (type(start) not in (int, float) or type(end) not in (int, float)
                        or not math.isfinite(start) or not math.isfinite(end)
                        or not 0 <= start < end or end * 1000 > duration_ms + 50
                        or not isinstance(speaker, str) or not speaker.strip() or len(speaker) > 100):
                    raise ValueError('Invalid turn')
                start_ms, end_ms = round(start * 1000), min(round(end * 1000), duration_ms)
                if start_ms >= end_ms:
                    raise ValueError('Invalid rounded interval')
                turns.append({'start_ms': start_ms, 'end_ms': end_ms, 'speaker_label': speaker})
            return sorted(turns, key=lambda item: (item['start_ms'], item['end_ms'], item['speaker_label']))
        except (KeyError, TypeError, ValueError) as exc:
            raise DiarizationError('DIARIZATION_INVALID_RESPONSE', '화자분리 결과의 시간·화자 정보를 확인하지 못했습니다.') from exc
