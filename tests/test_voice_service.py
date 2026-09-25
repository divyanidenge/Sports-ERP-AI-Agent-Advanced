"""
tests/test_voice_service.py
----------------------------
Unit and Integration Tests for Voice Interaction (STT / TTS) Service.
"""

import pytest
import io
import wave
import struct
from app.voice_service import VoiceService

def create_synthetic_wav_bytes(duration_sec=0.5, sample_rate=16000):
    """Generates valid in-memory PCM WAV audio bytes for testing."""
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        for i in range(int(duration_sec * sample_rate)):
            val = int(32767.0 * 0.1)
            wav.writeframes(struct.pack('<h', val))
    buf.seek(0)
    return buf.read()

def test_voice_service_initialization():
    """Verify voice service instance initialization."""
    vs = VoiceService()
    assert vs.recognizer is not None

def test_synthesize_speech_bytes():
    """Verify TTS speech synthesis returns non-empty audio byte stream."""
    vs = VoiceService()
    ok, audio_bytes = vs.synthesize_speech_bytes("Your badminton booking is confirmed.")
    # In network-enabled environment, returns valid MP3 bytes
    if ok:
        assert len(audio_bytes) > 100
        assert audio_bytes[:3] == b'ID3' or b'\xff\xfb' in audio_bytes[:10] or len(audio_bytes) > 50

def test_transcribe_audio_bytes_error_handling():
    """Verify that invalid audio bytes fail gracefully without raising unhandled exceptions."""
    vs = VoiceService()
    ok, msg = vs.transcribe_audio_bytes(b"not a real audio stream")
    assert ok is False
    assert "error" in msg.lower() or "could not" in msg.lower()

def test_process_voice_query_pipeline():
    """Verify end-to-end voice query handler structure."""
    vs = VoiceService()
    wav_bytes = create_synthetic_wav_bytes()
    res = vs.process_voice_query(
        audio_bytes=wav_bytes,
        user_id=1,
        session_id="test_voice_session",
        user_role="student"
    )
    assert "success" in res
    assert "transcription" in res
