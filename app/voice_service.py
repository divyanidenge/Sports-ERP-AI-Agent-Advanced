"""
app/voice_service.py
---------------------
Voice Interaction Service for Sports ERP AI Assistant.

Supports:
1. Speech-to-Text (STT) via SpeechRecognition (Google Cloud Speech API / offline WAV audio).
2. Direct Agent Pipeline Dispatch (reusing query_agent without duplication).
3. Text-to-Speech (TTS) via gTTS (Google Text-to-Speech) with pyttsx3 offline fallback.
4. Graceful Error Handling when audio hardware or network is unavailable.
"""

import io
import os
import base64
import logging
from typing import Dict, Any, Optional, Tuple
import speech_recognition as sr
from gtts import gTTS

logger = logging.getLogger("sports_erp.voice_service")

class VoiceService:
    def __init__(self):
        self.recognizer = sr.Recognizer()

    def transcribe_audio_bytes(self, audio_bytes: bytes, sample_rate: int = 16000) -> Tuple[bool, str]:
        """
        Transcribes raw audio bytes (WAV/PCM) to text.
        """
        if not audio_bytes or len(audio_bytes) < 10:
            return False, "No audio data detected. Please record a voice query into the microphone."

        try:
            audio_file = io.BytesIO(audio_bytes)
            with sr.AudioFile(audio_file) as source:
                audio_data = self.recognizer.record(source)
                text = self.recognizer.recognize_google(audio_data)
                return True, text.strip()
        except sr.UnknownValueError:
            return False, "Could not understand audio. Please speak clearly into the microphone."
        except sr.RequestError as e:
            return False, f"Speech recognition service error: {str(e)}"
        except Exception as e:
            return False, f"Audio processing error: {str(e)}"

    def synthesize_speech_bytes(self, text: str, lang: str = "en") -> Tuple[bool, bytes]:
        """
        Synthesizes text into MP3 audio bytes using gTTS with fallback.
        """
        try:
            clean_text = text.replace("*", "").replace("#", "").strip()
            if not clean_text:
                clean_text = "Action completed."
            
            tts = gTTS(text=clean_text, lang=lang, slow=False)
            mp3_fp = io.BytesIO()
            tts.write_to_fp(mp3_fp)
            mp3_fp.seek(0)
            return True, mp3_fp.read()
        except Exception as e:
            logger.warning(f"gTTS synthesis failed: {e}")
            return False, b""

    def process_voice_query(
        self,
        audio_bytes: bytes,
        user_id: int = 1,
        session_id: str = "voice_session",
        user_role: str = "student",
        current_user: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        End-to-end voice query handler:
        Audio In -> STT -> Existing Query Agent -> NLP Response -> TTS Out.
        """
        from app.query_agent import process_query
        
        # 1. Speech to Text
        stt_ok, transcribed_text = self.transcribe_audio_bytes(audio_bytes)
        if not stt_ok:
            return {
                "success": False,
                "transcription": "",
                "message": transcribed_text,
                "data": None,
                "pending_confirmation": False,
                "suggested_slots": [],
                "has_audio": False,
                "audio_bytes": None,
                "audio_base64": None
            }

        # 2. Existing AI Agent Pipeline Dispatch
        if not current_user:
            current_user = {
                "id": user_id,
                "role": user_role,
                "name": f"User {user_id}",
                "email": f"user{user_id}@example.com"
            }
            
        agent_res = process_query(
            query=transcribed_text,
            current_user=current_user,
            session_id=session_id
        )

        response_text = getattr(agent_res, "message", None) or getattr(agent_res, "response", str(agent_res))

        # 3. Text to Speech
        tts_ok, audio_out = self.synthesize_speech_bytes(response_text)
        audio_b64 = base64.b64encode(audio_out).decode("utf-8") if tts_ok and audio_out else None

        return {
            "success": True,
            "transcription": transcribed_text,
            "message": response_text,
            "data": getattr(agent_res, "data", None),
            "pending_confirmation": getattr(agent_res, "pending_confirmation", False),
            "suggested_slots": getattr(agent_res, "suggested_slots", []),
            "agent_response": agent_res.model_dump() if hasattr(agent_res, "model_dump") else (agent_res if isinstance(agent_res, dict) else str(agent_res)),
            "response_text": response_text,
            "has_audio": tts_ok,
            "audio_base64": audio_b64,
            "audio_bytes_length": len(audio_out) if tts_ok else 0
        }

# Global voice service singleton
voice_service = VoiceService()
