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
from app.voice_identifier import get_user_uid_by_user_id, save_user_voice_embedding_to_db

router = APIRouter()

BASE_DIR = "storage/audio"
WAV_DIR = os.path.join(BASE_DIR, "wav_chunks")
os.makedirs(WAV_DIR, exist_ok=True)

session_tempfiles = {}
session_mode = {}
user_voice_embeddings_mem = {}  # user_id: embedding
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

    CHUNK_DURATION_SEC = 2.0
    SAMPLE_RATE = 16000
    BYTES_PER_SEC = SAMPLE_RATE * 2  # 16bit(2byte) * 16000
    CHUNK_SIZE = int(CHUNK_DURATION_SEC * BYTES_PER_SEC)

    try:
        while True:
            msg = await websocket.receive()
            if msg.get("type") == "websocket.receive":
                if "text" in msg:
                    try:
                        data = json.loads(msg["text"])
                        event = data.get("event")
                        if event == "register_voice":
                            user_info = data.get("user_info", {})
                            user_id = user_info.get("user_id")
                            if user_id:
                                session_user_id[sid] = user_id
                            print(f"[register_user] 사용자 등록 요청: {user_info}")
                            print("[모드전환] register_user 신호 수신")
                            session_mode[sid] = "register_user"
                            await websocket.send_text(json.dumps({"event": "register_user", "status": "ok", "user_info": user_info}))
                        else:
                            print(f"알 수 없는 이벤트: {event}")
                    except Exception as e:
                        print(f"JSON 파싱/이벤트 처리 에러: {e}")
                elif "bytes" in msg:
                    chunk = msg["bytes"]
                    buffer.extend(chunk)
                    with open(temp_path, "ab") as f:
                        f.write(chunk)
                    # 분기: 등록용/일반 오디오
                    if session_mode.get(sid) == "register_user":
                        temp_path = session_tempfiles.pop(sid, None)
                        mode = session_mode.pop(sid, None)
                        print(f"mode: {mode}")
                        user_id = session_user_id.pop(sid, None)
                        if mode in ("register_user", "audio_data"):
                            try:
                                user_info = data.get("user_info", {}) if 'data' in locals() else {}
                                if not user_id:
                                    user_id = user_info.get("user_id")
                            except Exception as e:
                                print(f"[{mode}] user_info 추출 에러: {e}")
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

                            print(f"[register_user] 등록용 오디오 WAV 파일 경로: {wav_path}")

                            # 음성 임베딩 및 DB 저장
                            if user_id:
                                try:
                                    print(f"[register_user] 음성 임베딩 및 DB 저장 시작: user_id={user_id}")
                                    user_uid = get_user_uid_by_user_id(user_id)
                                    if user_uid is not None:
                                        embedding = save_user_voice_embedding_to_db(user_uid, wav_path)
                                        print(f"[register_user] 음성 임베딩 및 DB 저장 완료: user_uid={user_uid}")
                                        # 메모리에도 적재
                                        user_voice_embeddings_mem[user_id] = embedding
                                        print(f"[register_user] user_id={user_id} 임베딩을 메모리에 적재 완료.")
                                    else:
                                        print(f"[register_user] user_uid를 찾을 수 없음: user_id={user_id}")
                                except Exception as e:
                                    print(f"[register_user] 음성 임베딩/DB 저장 에러: {e}")
                            if mode == "register_user":
                                print(f"[register_user] 등록용 오디오 처리 완료")
                        else:
                            print(f"지원하지 않는 메시지 타입: {msg}")
                    else:
                        print(f"지원하지 않는 메시지 타입: {msg}")
                else:
                    print("지원하지 않는 메시지 타입")
    except WebSocketDisconnect:
        print(f"🔌 연결 해제: {websocket.client}")
    except Exception as e:
        # 연결 해제 후 receive로 인한 RuntimeError는 무시
        if isinstance(e, RuntimeError) and "Cannot call \"receive\" once a disconnect message has been received." in str(e):
            pass
        elif not isinstance(e, WebSocketDisconnect):
            print(f"❌ 에러: {e}")