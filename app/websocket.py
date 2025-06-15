import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from datetime import datetime
import os
import tempfile
import wave
from app.streaming_audio import google_stt_streaming, google_stt_sync, speech_client
from google.cloud import speech_v1p1beta1 as speech

router = APIRouter()

BASE_DIR = "storage/audio"
WAV_DIR = os.path.join(BASE_DIR, "wav_chunks")
os.makedirs(WAV_DIR, exist_ok=True)

session_tempfiles = {}

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    sid = id(websocket)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    wav_path = os.path.join(WAV_DIR, f"session_{ts}_{sid}.wav")
    temp_fd, temp_path = tempfile.mkstemp(suffix=".pcm")
    os.close(temp_fd)
    session_tempfiles[sid] = temp_path
    buffer = bytearray()
    print(f"🟢 연결됨: {websocket.client}")

    CHUNK_DURATION_SEC = 2.0
    SAMPLE_RATE = 16000
    BYTES_PER_SEC = SAMPLE_RATE * 2  # 16bit(2byte) * 16000
    CHUNK_SIZE = int(CHUNK_DURATION_SEC * BYTES_PER_SEC)

    try:
        while True:
            chunk = await websocket.receive_bytes()
            buffer.extend(chunk)
            with open(temp_path, "ab") as f:
                f.write(chunk)
            # 2초 분량이 쌓이면 STT
            while len(buffer) >= CHUNK_SIZE:
                chunk_bytes = buffer[:CHUNK_SIZE]
                del buffer[:CHUNK_SIZE]
                transcript = google_stt_streaming(chunk_bytes)
                if transcript:
                    await websocket.send_text(f"실시간 STT: {transcript}")
    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"❌ 에러: {e}")
    finally:
        print(f"🔌 연결 해제: {websocket.client}")
        temp_path = session_tempfiles.pop(sid, None)
        if temp_path and os.path.exists(temp_path):
            with open(temp_path, "rb") as f:
                pcm_bytes = f.read()
            # WAV 헤더 붙여서 새 파일로 저장
            with wave.open(wav_path, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(pcm_bytes)
            os.remove(temp_path)
            with open(wav_path, "rb") as f:
                full_audio = f.read()
            final_result = google_stt_sync(full_audio)
            print(f"[최종 STT] {final_result}") 