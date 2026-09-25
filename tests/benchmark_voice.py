"""
tests/benchmark_voice.py
-------------------------
Reproducible Latency & Pipeline Benchmark for Voice Interaction Service.
"""

import os
import sys
import json
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.voice_service import VoiceService

def run_voice_benchmark():
    print("=" * 70)
    print("[*] RUNNING VOICE INTERACTION PIPELINE BENCHMARK")
    print("=" * 70)

    vs = VoiceService()
    test_phrases = [
        "Show my active court bookings.",
        "Which sports facilities are available today?",
        "How busy will badminton courts be tomorrow at 5 PM?",
        "Your badminton court booking is confirmed for tomorrow."
    ]

    tts_latencies = []
    for phrase in test_phrases:
        t0 = time.perf_counter()
        ok, audio_bytes = vs.synthesize_speech_bytes(phrase)
        elapsed = (time.perf_counter() - t0) * 1000
        tts_latencies.append({
            "phrase": phrase,
            "success": ok,
            "audio_size_bytes": len(audio_bytes),
            "tts_latency_ms": round(elapsed, 2)
        })
        print(f"[+] TTS Synthesis: '{phrase[:30]}...' -> {len(audio_bytes)} bytes in {elapsed:.2f} ms")

    avg_latency = round(sum(item["tts_latency_ms"] for item in tts_latencies) / len(tts_latencies), 2)
    
    benchmark_out = {
        "engine": "gTTS / pyttsx3",
        "average_tts_latency_ms": avg_latency,
        "results": tts_latencies
    }

    with open("voice_benchmark_results.json", "w", encoding="utf-8") as f:
        json.dump(benchmark_out, f, indent=2)
    print(f"\n[+] Saved voice benchmark to voice_benchmark_results.json")

if __name__ == "__main__":
    run_voice_benchmark()
