# Standard library imports
import asyncio
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

    # --- 병렬 처리 및 순서 보장을 위한 변수 ---
    # 각 청크에 고유 ID를 부여
    chunk_id_counter = 0 
    # 처리 결과를 저장 (key: chunk_id, value: result)
    results = {}
    # 다음으로 전송해야 할 청크의 ID
    next_chunk_to_send = 0
    # 결과 전송 루프를 제어하기 위한 이벤트
    stop_event = asyncio.Event()

    user_id_for_session = None
    sender_task = None

    # 처리 결과를 순서대로 전송하는 비동기 함수 (소비자)
    async def send_results_in_order():
        nonlocal next_chunk_to_send
        while not stop_event.is_set():
            if next_chunk_to_send in results:
                result = results.pop(next_chunk_to_send)
                if result:  # 타임아웃으로 None이 저장된 경우는 전송하지 않음
                    try:
                        print(f"[통역결과전달][{result}]")
                        await websocket.send_text(json.dumps(result, ensure_ascii=False))
                    except WebSocketDisconnect:
                        break # 전송 중 연결이 끊어지면 루프 종료
                next_chunk_to_send += 1
            else:
                await asyncio.sleep(0.01) # CPU 부하를 줄이기 위해 잠시 대기

    # 개별 청크를 타임아웃과 함께 처리하는 비동기 함수
    async def process_chunk_with_timeout(chunk_id, chunk_data, user_id, user_embedding):
        try:
            # 10초 타임아웃 설정
            # `process_realtime_chunk`가 이제 비동기 함수이므로 직접 await 합니다.
            analysis_result = await asyncio.wait_for(
                analyze_service.process_realtime_chunk(chunk_data, user_id, user_embedding),
                timeout=10.0
            )
            results[chunk_id] = analysis_result
        except asyncio.TimeoutError:
            print(f"Chunk {chunk_id} 처리 시간 초과 (10초). 해당 요청을 버립니다.")
            results[chunk_id] = None # 타임아웃된 작업 표시
        except Exception as e:
            print(f"Chunk {chunk_id} 처리 중 에러: {e}")
            results[chunk_id] = None


    try:
        # 1. 초기 설정 메시지 처리
        setup_data = await websocket.receive_json()
        response_data, user_id = await analyze_service.handle_setup_message(sid, setup_data, session_user_id, user_voice_embeddings_mem)
        
        if response_data.get("status") == "error":
            await websocket.close(code=1008, reason=response_data.get("message"))
            return
        
        await websocket.send_text(json.dumps(response_data))
        user_id_for_session = user_id

        # 결과 전송 루프 시작
        sender_task = asyncio.create_task(send_results_in_order())

        # 2. 실시간 음성 데이터 처리 루프 (생산자)
        while True:
            chunk = await websocket.receive_bytes()
            buffer.extend(chunk)
            full_audio_buffer.extend(chunk)

            while len(buffer) >= CHUNK_SIZE:
                chunk_to_process = buffer[:CHUNK_SIZE]
                del buffer[:CHUNK_SIZE]
                
                user_embedding = user_voice_embeddings_mem.get(user_id_for_session)
                
                # 각 청크를 병렬 처리 작업으로 생성
                asyncio.create_task(
                    process_chunk_with_timeout(
                        chunk_id_counter, chunk_to_process, user_id_for_session, user_embedding
                    )
                )
                chunk_id_counter += 1

    except WebSocketDisconnect:
        print(f"🔌 연결 해제 (sid: {sid})")
    except Exception as e:
        if not isinstance(e, WebSocketDisconnect):
            print(f"❌ 예상치 못한 에러 (sid: {sid}): {e}")
    finally:
        # 3. 후처리 및 세션 정리
        print(f"🔌 후처리 시작 (sid: {sid}). 수신된 총 데이터 크기: {len(full_audio_buffer)} bytes")
        
        # 백그라운드 작업들을 안전하게 종료
        stop_event.set()
        if sender_task:
            await sender_task

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