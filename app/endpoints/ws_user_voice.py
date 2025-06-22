# Standard library imports
import json
import os
import tempfile
import wave
from datetime import datetime

# Third-party imports
from fastapi import APIRouter, WebSocket
from starlette.websockets import WebSocketDisconnect

# Local application imports
from app.services.user_services import user_service
from app.services.user_voice_service import user_voice_service
from .ws_analyze import user_voice_embeddings_mem

router = APIRouter()

BASE_DIR = "storage/audio"
WAV_DIR = os.path.join(BASE_DIR, "wav_chunks")
os.makedirs(WAV_DIR, exist_ok=True)

session_tempfiles = {}
session_mode = {}
session_user_id = {}

@router.websocket("/ws/users")
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

    try:
        # 1. 설정 메시지 수신
        setup_data = await websocket.receive_json()
        event = setup_data.get("event")
        print(f"🟢 이벤트: {event}")

        if event == "register_voice":
            user_info = setup_data.get("user_info", {})
            user_id = user_info.get("user_id")
            if user_id:
                session_user_id[sid] = user_id
            print(f"[register_voice] 사용자 음성 등록 요청: {user_info}")
            session_mode[sid] = "register_voice"
            await websocket.send_text(
                json.dumps({"event": "register_voice", "status": "ok", "user_info": user_info})
            )
        else:
            print(f"잘못된 시작 이벤트 '{event}'. 연결을 종료합니다.")
            await websocket.close(code=1008)
            return

        # 2. 데이터 스트림 수신
        while True:
            audio_bytes = await websocket.receive_bytes()
            buffer.extend(audio_bytes)
            
    except WebSocketDisconnect:
        print(f"🔌 연결 해제: {websocket.client}")
        
        if session_mode.get(sid) == "register_voice" and buffer:
            user_id = session_user_id.get(sid)
            with wave.open(wav_path, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(buffer)

            print(f"[register_voice] 등록용 오디오 WAV 파일 저장 완료: {wav_path}")

            if user_id:
                try:
                    print(f"[register_voice] 음성 임베딩 및 DB 저장 시작: user_id={user_id}")
                    user_uid = user_service.get_user_uid_by_user_id(user_id)
                    if user_uid is not None:
                        embedding = user_voice_service.register_user_voice(user_uid, wav_path)
                        print(f"[register_voice] 음성 임베딩 및 DB 저장 완료: user_uid={user_uid}")
                        user_voice_embeddings_mem[user_id] = embedding
                        print(f"[register_voice] user_id={user_id} 임베딩을 메모리에 적재 완료.")
                    else:
                        print(f"[register_voice] user_uid를 찾을 수 없음: user_id={user_id}")
                except Exception as e:
                    print(f"[register_voice] 음성 임베딩/DB 저장 에러: {e}")
        else:
            print("[register_voice] 받은 오디오 데이터가 없습니다.")

    except Exception as e:
        if not isinstance(e, WebSocketDisconnect):
            print(f"❌ 에러: {e}")
    finally:
        if sid in session_tempfiles:
             os.remove(session_tempfiles[sid])
             del session_tempfiles[sid]
        if sid in session_mode:
            del session_mode[sid]
        if sid in session_user_id:
            del session_user_id[sid]