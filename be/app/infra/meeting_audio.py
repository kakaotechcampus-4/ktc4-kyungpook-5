"""Rebuild saved speech WAV chunks on their original meeting timeline."""

import io
import wave
from collections.abc import Iterable
from typing import BinaryIO

MAX_MEETING_MS = 4 * 60 * 60 * 1000
BYTES_PER_MS = 32


def assemble_meeting_wav(chunks: Iterable[tuple[int, int, bytes]], output: BinaryIO) -> int:
    """Write 16kHz mono PCM, retaining gaps; input must be ordered by time.

    shortcut: bounded to four hours, increase after measuring worker memory/latency.
    The caller owns and deletes the temporary output after provider submission.
    """
    cursor = 0
    found = False
    with wave.open(output, 'wb') as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(16000)
        for start_ms, end_ms, content in chunks:
            if (type(start_ms) is not int or type(end_ms) is not int
                    or not 0 <= cursor <= start_ms < end_ms <= MAX_MEETING_MS):
                raise ValueError('Invalid or overlapping meeting audio timestamps')
            with wave.open(io.BytesIO(content), 'rb') as source:
                if (source.getnchannels(), source.getsampwidth(), source.getframerate(), source.getcomptype()) != (1, 2, 16000, 'NONE'):
                    raise ValueError('Expected 16kHz mono PCM16 WAV')
                expected_bytes = (end_ms - start_ms) * BYTES_PER_MS
                if source.getnframes() * 2 != expected_bytes:
                    raise ValueError('Audio duration does not match saved timestamps')
                gap_bytes = (start_ms - cursor) * BYTES_PER_MS
                while gap_bytes:
                    size = min(gap_bytes, 65536)
                    target.writeframesraw(bytes(size))
                    gap_bytes -= size
                remaining = expected_bytes
                while remaining:
                    block = source.readframes(min(remaining // 2, 32768))
                    if not block:
                        raise ValueError('Truncated meeting audio')
                    target.writeframesraw(block)
                    remaining -= len(block)
            cursor = end_ms
            found = True
    if not found:
        raise ValueError('No saved meeting audio')
    return cursor
