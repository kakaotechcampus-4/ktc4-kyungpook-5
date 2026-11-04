import io
import wave

from app.routers.meetings import _crop_wav
from app.schemas.meetings import ReviewCandidatesIn, SpeakerNamesIn


def test_review_input_uses_camel_case_and_speaker_confirmation():
    body = ReviewCandidatesIn.model_validate({
        'expectedVersion': 2,
        'clientRequestId': 'save-1',
        'candidates': [{
            'title': '장소 예약', 'assigneeMemberId': 'mbr_1',
            'dueDate': '2026-11-08', 'evidenceSegmentIds': ['tsg_1'],
        }],
    })
    speakers = SpeakerNamesIn.model_validate({
        'expectedVersion': 2,
        'members': {'SPEAKER_00': {'memberId': 'mbr_1', 'confirmed': True}},
    })
    assert body.candidates[0].assignee_member_id == 'mbr_1'
    assert speakers.members['SPEAKER_00'].confirmed is True


def test_audio_clip_keeps_requested_duration():
    source = io.BytesIO()
    with wave.open(source, 'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b'\x01\x00' * 1600)
    clipped = _crop_wav(source.getvalue(), chunk_start_ms=100, start_ms=150, end_ms=175)
    with wave.open(io.BytesIO(clipped), 'rb') as wav:
        assert wav.getnframes() == 400
