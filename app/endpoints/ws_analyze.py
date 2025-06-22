# Standard library imports
import io
import json
import os
import tempfile
import time
import wave
from datetime import datetime

# Third-party imports
from fastapi import APIRouter, WebSocket
from starlette.websockets import WebSocketDisconnect

# Local application imports
from app.services.analyze_service import analyze_service

router = APIRouter()

BASE_DIR = "storage/audio"
WAV_DIR = os.path.join(BASE_DIR, "wav_chunks")
os.makedirs(WAV_DIR, exist_ok=True)

# --- 세션 관리를 위한 메모리 내 저장소 ---
# user_voice_embeddings_mem: 사용자 음성 임베딩 캐시
# session_user_id: 웹소켓 세션(sid)과 사용자 ID 매핑
session_tempfiles = {}
session_user_id = {}
user_voice_embeddings_mem = {}


@router.websocket("/ws/analyze")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    sid = id(websocket)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    
    # 세션별 파일 및 버퍼 초기화
    wav_path = os.path.join(WAV_DIR, f"session_{ts}_{sid}.wav")
    temp_fd, temp_path = tempfile.mkstemp(suffix=".pcm")
    os.close(temp_fd)
    session_tempfiles[sid] = temp_path
    
    buffer = bytearray()
    full_audio_buffer = bytearray()
    
    print(f"🟢 연결됨: {websocket.client} (sid: {sid})")

    # 상수 정의
    CHUNK_DURATION_SEC = 2.0
    SAMPLE_RATE = 16000
    BYTES_PER_SEC = SAMPLE_RATE * 2  # 16bit(2byte) * 16000
    CHUNK_SIZE = int(CHUNK_DURATION_SEC * BYTES_PER_SEC)

    user_id_for_session = None

    try:
        # 1. 초기 설정 메시지 처리
        setup_data = await websocket.receive_json()
        response_data, user_id = await analyze_service.handle_setup_message(sid, setup_data, session_user_id, user_voice_embeddings_mem)
        
        if response_data.get("status") == "error":
            await websocket.close(code=1008, reason=response_data.get("message"))
            return
        
        await websocket.send_text(json.dumps(response_data))
        user_id_for_session = user_id

        # 2. 실시간 음성 데이터 처리 루프
        while True:
            chunk = await websocket.receive_bytes()
            buffer.extend(chunk)
            full_audio_buffer.extend(chunk)

            while len(buffer) >= CHUNK_SIZE:
                chunk_to_process = buffer[:CHUNK_SIZE]
                del buffer[:CHUNK_SIZE]
                
                user_embedding = user_voice_embeddings_mem.get(user_id_for_session)
                analysis_result = analyze_service.process_realtime_chunk(chunk_to_process, user_id_for_session, user_embedding)

                if analysis_result:
                    await websocket.send_text(json.dumps(analysis_result, ensure_ascii=False))

    except WebSocketDisconnect:
        print(f"🔌 연결 해제 (sid: {sid})")
    except Exception as e:
        if not isinstance(e, WebSocketDisconnect):
            print(f"❌ 예상치 못한 에러 (sid: {sid}): {e}")
    finally:
        # 3. 후처리 및 세션 정리
        print(f"🔌 후처리 시작 (sid: {sid}). 수신된 총 데이터 크기: {len(full_audio_buffer)} bytes")
        
        analyze_service.finalize_analysis(
            wav_path=wav_path,
            full_audio_buffer=full_audio_buffer,
            user_id=user_id_for_session,
            sid=sid,
            ts=ts,
            user_voice_embeddings_mem=user_voice_embeddings_mem
        )
        
        # 세션 관련 데이터 정리
        temp_file_to_remove = session_tempfiles.pop(sid, None)
        if temp_file_to_remove and os.path.exists(temp_file_to_remove):
            os.remove(temp_file_to_remove)
        session_user_id.pop(sid, None)
        # user_voice_embeddings_mem은 캐시이므로 유지
        
        print(f"세션 정리 완료 (sid: {sid}).")