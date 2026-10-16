"""회의 음성 청크 STT의 더미 구현.

실제 VAD·Whisper 연동은 #118 범위다. 그 전까지 음성 청크 업로드 → 전사 → 판단
흐름이 끝까지 도는지만 확인하도록 청크 정보로 고정 문장을 만든다. 음성 내용을
알아듣는 척하지 않는다 — 문장이 더미임을 그대로 드러낸다.
"""


def transcribe_chunk(*, seq: int, start_ms: int, end_ms: int) -> str:
    return f"(더미 전사) {seq}번 음성 청크 {start_ms}~{end_ms}ms 구간입니다."
