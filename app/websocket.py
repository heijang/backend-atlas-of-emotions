import asyncio
from fastapi import APIRouter, WebSocket
from starlette.websockets import WebSocketDisconnect
from datetime import datetime
import os
import tempfile
import wave
from app.streaming_audio import get_streaming_stt_provider, get_sync_stt_provider
import json
from app.voice_identifier import save_user_voice_embedding_to_db, load_user_voice_embedding_to_memory, compare_voice_with_memory, get_user_uid_by_user_id
import librosa
from app.emotion_analyzer import analyze_emotions
from app.audio_utils import cut_wav_by_timestamps, get_storage_audio_path
from app.persistence.report_dao import ReportDAO

router = APIRouter()

BASE_DIR = "storage/audio"
WAV_DIR = os.path.join(BASE_DIR, "wav_chunks")
os.makedirs(WAV_DIR, exist_ok=True)

session_tempfiles = {}
session_mode = {}
user_voice_embeddings_mem = {}  # user_id: embedding
session_user_id = {}

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
            msg = await websocket.receive()
            if msg.get("type") == "websocket.receive":
                if "text" in msg:
                    try:
                        data = json.loads(msg["text"])
                        event = data.get("event")
                        if event == "register_user":
                            user_info = data.get("user_info", {})
                            user_id = user_info.get("user_id")
                            if user_id:
                                session_user_id[sid] = user_id
                            print(f"[register_user] 사용자 등록 요청: {user_info}")
                            print("[모드전환] register_user 신호 수신")
                            session_mode[sid] = "register_user"
                            await websocket.send_text(json.dumps({"event": "register_user", "status": "ok", "user_info": user_info}))
                        elif event == "audio_data":
                            user_info = data.get("user_info", {})
                            user_id = user_info.get("user_id")
                            if user_id:
                                session_user_id[sid] = user_id
                                # 음성 임베딩이 메모리에 없으면 DB에서 조회하여 적재
                                if user_id not in user_voice_embeddings_mem:
                                    print(f"[음성 임베딩] user_id={user_id} 메모리에 없음. DB 조회 시도...")
                                    embedding = load_user_voice_embedding_to_memory(user_id)
                                    if embedding is not None:
                                        user_voice_embeddings_mem[user_id] = embedding
                                        print(f"[음성 임베딩] user_id={user_id} DB에서 조회하여 메모리에 적재 완료.")
                                    else:
                                        print(f"[음성 임베딩] user_id={user_id} DB에도 임베딩 정보가 없음.")
                            else:
                                print(f"[디버그] audio_data 이벤트에서 user_id가 전달되지 않음! sid={sid}")
                            print(f"[audio_data] 사용자 음성 데이터 요청: {user_info}")
                            print("[모드전환] audio_data 신호 수신")
                            session_mode[sid] = "audio_data"
                            await websocket.send_text(json.dumps({"event": "audio_data", "status": "ok"}))
                        elif event == "login":
                            pass  # login 이벤트는 더 이상 처리하지 않음
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
                        # 등록용 오디오 처리: 파일에 저장만 하고, 실시간 STT는 하지 않음
                        pass  # 불필요한 상세 로깅 제거
                    else:
                        # 일반 오디오 처리 (실시간 STT)
                        while len(buffer) >= CHUNK_SIZE:
                            chunk_bytes = buffer[:CHUNK_SIZE]
                            del buffer[:CHUNK_SIZE]
                            transcript = get_streaming_stt_provider().streaming(chunk_bytes)
                            if transcript:
                                # await websocket.send_text(f"{transcript}")
                                # 감정 분석 추가
                                # chunk_bytes는 PCM(16kHz, 16bit, mono) -> WAV로 변환 후 numpy array로 변환 필요
                                import io
                                import numpy as np
                                with io.BytesIO() as wav_io:
                                    with wave.open(wav_io, 'wb') as wf:
                                        wf.setnchannels(1)
                                        wf.setsampwidth(2)
                                        wf.setframerate(16000)
                                        wf.writeframes(chunk_bytes)
                                    wav_io.seek(0)
                                    audio_array, _ = librosa.load(wav_io, sr=16000, mono=True)
                                emotion_result = analyze_emotions(transcript, audio_array)
                                # 음성 유사도 식별
                                user_id = session_user_id.get(sid)
                                user_embedding = user_voice_embeddings_mem.get(user_id)
                                similarity = None
                                is_same = None
                                if user_embedding is not None:
                                    # chunk_bytes를 임시 wav 파일로 저장
                                    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_wav:
                                        with wave.open(temp_wav.name, 'wb') as wf:
                                            wf.setnchannels(1)
                                            wf.setsampwidth(2)
                                            wf.setframerate(16000)
                                            wf.writeframes(chunk_bytes)
                                        temp_wav_path = temp_wav.name
                                    try:
                                        is_same, similarity = compare_voice_with_memory(temp_wav_path, user_embedding, threshold=0.5)
                                    except Exception as e:
                                        print(f"[실시간 음성 식별 에러] {e}")
                                    finally:
                                        os.remove(temp_wav_path)
                                else:
                                    print(f"[실시간 음성 식별] user_id={user_id} 메모리 내 임베딩 정보 없음.")

                                # emotion_analysis와 voice_similarity 결과를 하나의 응답으로 통합
                                await websocket.send_text(json.dumps({
                                    "event": "emotion_analysis",
                                    "transcript": transcript,
                                    "emotion": emotion_result,
                                    "is_same": is_same,
                                    "similarity": similarity
                                }, ensure_ascii=False))
                                print(f"[실시간 STT] {transcript}")
                                print(f"[실시간 감정분석 결과] {json.dumps(emotion_result, ensure_ascii=False)}")
                                print(f"[실시간 음성 유사도] similarity={similarity}, is_same={is_same}")
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
    finally:
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
            if mode == "register_user":
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
            elif mode == "audio_data":
                with open(wav_path, "rb") as f:
                    full_audio = f.read()
                final_result = get_sync_stt_provider().sync(full_audio)
                if isinstance(final_result, list):
                    print("[최종 STT - Clova diarization 결과]")
                    # DB 저장 로직 추가
                    user_id_for_db = user_id if user_id else "test_user"
                    user_uid_for_db = get_user_uid_by_user_id(user_id_for_db)
                    report_dao = ReportDAO()
                    master_uid = None
                    try:
                        # 마스터 row 생성 (topic은 None 또는 자동 생성)
                        master_uid = report_dao.insert_conversation_master(user_uid_for_db, topic=None)
                        print(f"[DB] user_conversation_master 저장: master_uid={master_uid}")
                    except Exception as e:
                        print(f"[DB] master 저장 에러: {e}")
                    # 음성 임베딩 비교 로직 추가
                    if not user_id:
                        print(f"[디버그] audio_data 모드에서 user_id가 세션에 없음! test_user로 대체됨. sid={sid}")
                        user_id = "test_user"  # 임시 테스트용
                    user_embedding = user_voice_embeddings_mem.get(user_id)
                    if user_embedding is None:
                        print(f"[음성 식별] user_id={user_id} 메모리 내 임베딩 정보 없음.")
                    segment_timestamps = []
                    for seg in final_result:
                        start = seg.get('start')
                        end = seg.get('end')
                        if start is not None and end is not None:
                            start_sec = start / SAMPLE_RATE
                            end_sec = end / SAMPLE_RATE
                            segment_timestamps.append((start_sec, end_sec))
                    segment_dir = get_storage_audio_path(f"segments/{ts}_{sid}")
                    segment_files = cut_wav_by_timestamps(wav_path, segment_timestamps, segment_dir)
                    print(f"[문장별 오디오 컷팅 경로] {segment_files}")
                    import json as _json
                    for i, seg in enumerate(final_result):
                        print(f"[Segment {i+1}] Speaker: {seg.get('speaker')} | Text: {seg.get('text')}")
                        try:
                            seg_wav_path = segment_files[i] if i < len(segment_files) else wav_path
                            is_same, similarity = compare_voice_with_memory(seg_wav_path, user_embedding, threshold=0.75)
                            print(f"[음성 식별] Segment {i+1} | 유사도: {similarity:.4f} | 동일인: {is_same} | 파일: {seg_wav_path}")
                            # DB에 detail 저장
                            if master_uid:
                                try:
                                    report_dao.insert_conversation_detail(
                                        master_uid=master_uid,
                                        sentence=seg.get('text'),
                                        speaker=str(seg.get('speaker', {}).get('label')) if isinstance(seg.get('speaker'), dict) else str(seg.get('speaker')),
                                        emotion_score=_json.dumps(seg.get('emotion_score', {}), ensure_ascii=False),
                                        emotion_text=seg.get('emotion_text', None),
                                        audio_path=seg_wav_path
                                    )
                                    print(f"[DB] user_conversation_detail 저장: master_uid={master_uid}, seg_idx={i}")
                                except Exception as e:
                                    print(f"[DB] detail 저장 에러: {e}")
                        except Exception as e:
                            print(f"[음성 식별] Segment {i+1} | 에러: {e}")
                    try:
                        report_dao.close()
                    except Exception:
                        pass
                else:
                    print(f"[최종 STT] {final_result}") 