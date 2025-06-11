from fastapi import APIRouter, WebSocket
from datetime import datetime
import os
from pathlib import Path
from app.audio_utils import convert_webm_to_wav, split_wav_by_silence

router = APIRouter()

# 경로 및 폴더 생성
WEBM_DIR = "webm_chunks"
WAV_DIR = "wav_chunks"
SEGMENT_DIR = "split_segments"
os.makedirs(WEBM_DIR, exist_ok=True)
os.makedirs(WAV_DIR, exist_ok=True)
os.makedirs(SEGMENT_DIR, exist_ok=True)

SILENCE_THRESHOLD = "-35dB"
SILENCE_DURATION = 0.7

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print(f"🟢 연결됨: {websocket.client}")
    try:
        while True:
            message = await websocket.receive_bytes()
            ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            webm_path = f"{WEBM_DIR}/chunk_{ts}.webm"
            wav_path = f"{WAV_DIR}/chunk_{ts}.wav"

            # 1. 저장
            with open(webm_path, "wb") as f:
                f.write(message)
            print(f"📥 WebM 저장됨: {webm_path}")

            # 2. 변환
            convert_webm_to_wav(webm_path, wav_path)
            print(f"🎧 WAV 변환 완료: {wav_path}")

            # 3. 분할
            segments = split_wav_by_silence(wav_path, SEGMENT_DIR, SILENCE_THRESHOLD, SILENCE_DURATION)
            print(f"✂️ 분할 완료 ({len(segments)}개):", segments)

            await websocket.send_text(f"분할 완료: {len(segments)}개")
    except Exception as e:
        print(f"❌ 에러: {e}")
        await websocket.close() 