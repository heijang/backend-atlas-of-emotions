# Standard library imports
import io
import json
import os
import tempfile
import time
import wave
from datetime import datetime

# Third-party imports
import librosa
from fastapi import APIRouter, WebSocket
from starlette.websockets import WebSocketDisconnect

# Local application imports
from app.dao.user_conversation_dao import UserConversationDAO
from app.providers.gemini_client import analyze_emotions
from app.providers.stt_provider import get_streaming_stt_provider, get_sync_stt_provider
from app.utils.audio_utils import cut_wav_by_timestamps, get_storage_audio_path
from app.services.user_services import user_service
from app.services.user_voice_service import user_voice_service

router = APIRouter()

BASE_DIR = "storage/audio"
WAV_DIR = os.path.join(BASE_DIR, "wav_chunks")
os.makedirs(WAV_DIR, exist_ok=True)

session_tempfiles = {}
session_mode = {}
user_voice_embeddings_mem = {}  # user_id: embedding
session_user_id = {}

@router.websocket("/ws/analyze")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    sid = id(websocket)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    wav_path = os.path.join(WAV_DIR, f"session_{ts}_{sid}.wav")
    temp_fd, temp_path = tempfile.mkstemp(suffix=".pcm")
    os.close(temp_fd)
    session_tempfiles[sid] = temp_path
    buffer = bytearray()
    full_audio_buffer = bytearray()
    print(f"🟢 연결됨: {websocket.client}")

    CHUNK_DURATION_SEC = 2.0
    SAMPLE_RATE = 16000
    BYTES_PER_SEC = SAMPLE_RATE * 2  # 16bit(2byte) * 16000
    CHUNK_SIZE = int(CHUNK_DURATION_SEC * BYTES_PER_SEC)

    report_dao = UserConversationDAO()
    master_uid = None

    try:
        setup_data = await websocket.receive_json()
        event = setup_data.get("event")
        if event == "send_conversation":
            user_info = setup_data.get("user_info", {})
            user_id = user_info.get("user_id")
            if user_id:
                session_user_id[sid] = user_id
                if user_id not in user_voice_embeddings_mem:
                    print(f"[음성 임베딩] user_id={user_id} 메모리에 없음. DB 조회 시도...")
                    user_uid = user_service.get_user_uid_by_user_id(user_id)
                    if user_uid:
                        embedding = user_voice_service.get_user_voice_embedding(user_uid)
                        if embedding is not None:
                            user_voice_embeddings_mem[user_id] = embedding
                            print(f"[음성 임베딩] user_id={user_id} DB에서 조회하여 메모리에 적재 완료.")
                        else:
                            print(f"[음성 임베딩] user_id={user_id} DB에도 임베딩 정보가 없음.")
                    else:
                        print(f"[음성 임베딩] user_id={user_id} 에 해당하는 user_uid 없음.")
            session_mode[sid] = event
            await websocket.send_text(json.dumps({"event": "send_conversation", "status": "ok"}))
        else:
            print(f"알 수 없는 이벤트: {event}")
            await websocket.close(code=1008)
            return

        while True:
            chunk = await websocket.receive_bytes()
            buffer.extend(chunk)
            full_audio_buffer.extend(chunk)

            while len(buffer) >= CHUNK_SIZE:
                chunk_bytes = buffer[:CHUNK_SIZE]
                del buffer[:CHUNK_SIZE]
                transcript = get_streaming_stt_provider().streaming(chunk_bytes)
                if transcript:
                    # 감정 분석 추가
                    # chunk_bytes는 PCM(16kHz, 16bit, mono) -> WAV로 변환 후 numpy array로 변환 필요
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
                            is_same, similarity = user_voice_service.compare_voice(temp_wav_path, user_embedding, threshold=0.5)
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

    except WebSocketDisconnect:
        print(f"🔌 연결 해제 (데이터 수신 완료)")
    except Exception as e:
        if not isinstance(e, WebSocketDisconnect):
            print(f"❌ 예상치 못한 에러: {e}")
    finally:
        print(f"🔌 후처리 시작. 수신된 총 데이터 크기: {len(full_audio_buffer)} bytes")
        mode = session_mode.pop(sid, None)
        user_id = session_user_id.pop(sid, None)

        if mode == "send_conversation" and len(full_audio_buffer) > 0:
            # 전체 PCM 데이터를 WAV 파일로 저장
            with wave.open(wav_path, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(full_audio_buffer)
            
            # 후처리: STT 분석 및 DB 저장
            with open(wav_path, "rb") as f:
                full_audio = f.read()
            # Clova STT 분석
            clova_start = time.time()
            print(f"[Clova 분석] 요청 시작: {clova_start}")
            final_result = get_sync_stt_provider().sync(full_audio)
            clova_end = time.time()
            print(f"[Clova 분석] 요청 종료: {clova_end}, 소요시간: {clova_end - clova_start:.2f}초")
            if isinstance(final_result, list):
                print("[최종 STT - Clova diarization 결과]")
                # DB 저장 로직 추가
                user_id_for_db = user_id if user_id else "test_user"
                user_uid_for_db = user_service.get_user_uid_by_user_id(user_id_for_db)
                master_uid = report_dao.insert_conversation_master(user_uid_for_db, topic=None)
                print(f"[DB] user_conversation_master 저장: master_uid={master_uid}")
                user_embedding = user_voice_embeddings_mem.get(user_id)
                if user_embedding is None:
                    print(f"[음성 식별] user_id={user_id} 메모리 내 임베딩 정보 없음.")
                segment_timestamps = [(seg.get('start') / 1000, seg.get('end') / 1000) for seg in final_result]
                segment_dir = get_storage_audio_path(f"segments/{ts}_{sid}")
                segment_files = cut_wav_by_timestamps(wav_path, segment_timestamps, segment_dir)
                print(f"[문장별 오디오 컷팅 경로] {segment_files}")
                for i, seg in enumerate(final_result):
                    print(f"[Segment {i+1}] Speaker: {seg.get('speaker')} | Text: {seg.get('text')}")
                    try:
                        seg_wav_path = segment_files[i] if i < len(segment_files) else wav_path
                        is_same, similarity = user_voice_service.compare_voice(seg_wav_path, user_embedding, threshold=0.75)
                        print(f"[음성 식별] Segment {i+1} | 유사도: {similarity:.4f} | 동일인: {is_same} | 파일: {seg_wav_path}")
                        # Gemini 감정분석 시간 측정
                        gemini_start = time.time()
                        print(f"[Gemini 분석] 요청 시작: {gemini_start}")
                        # DB에 detail 저장
                        if master_uid:
                            try:
                                # emotion_result: 전체 감정분석 결과
                                # dominant_emotion: audio.scores에서 가장 높은 값의 key
                                emotion_result = seg.get('emotion_result')
                                if not emotion_result:
                                    # backward compatibility: seg에 emotion_score만 있을 경우
                                    emotion_result = {}
                                else:
                                    # 이미 emotion_result가 dict로 들어온 경우 그대로 사용
                                    pass
                                # dominant_emotion 추출
                                dominant_emotion = None
                                if emotion_result and 'audio' in emotion_result and 'scores' in emotion_result['audio']:
                                    scores = emotion_result['audio']['scores']
                                    if isinstance(scores, dict):
                                        # 값이 str일 수도 있으니 float 변환
                                        try:
                                            dominant_emotion = max(scores, key=lambda k: float(scores[k]))
                                        except Exception:
                                            dominant_emotion = None
                                report_dao.insert_conversation_detail(
                                    master_uid=master_uid,
                                    sentence=seg.get('text'),
                                    speaker=str(seg.get('speaker', {}).get('label')) if isinstance(seg.get('speaker'), dict) else str(seg.get('speaker')),
                                    emotion_result=json.dumps(emotion_result, ensure_ascii=False),
                                    dominant_emotion=dominant_emotion,
                                    start_ms=seg.get('start'),
                                    end_ms=seg.get('end')
                                )
                                gemini_end = time.time()
                                print(f"[Gemini 분석] 요청 종료: {gemini_end}, 소요시간: {gemini_end - gemini_start:.2f}초")
                                print(f"[DB] user_conversation_detail 저장: master_uid={master_uid}, seg_idx={i}")
                            except Exception as e:
                                print(f"[DB] detail 저장 에러: {e}")
                    except Exception as e:
                        print(f"[음성 식별] Segment {i+1} | 에러: {e}")
                if master_uid:
                    try:
                        report_dao.update_master_audio_path(master_uid, wav_path)
                        print(f"[DB] user_conversation_master.audio_path 업데이트: master_uid={master_uid}")
                    except Exception as e:
                        print(f"[DB] master.audio_path 업데이트 에러: {e}")

                try:
                    report_dao.close()
                except Exception:
                    pass
            else:
                print(f"[최종 STT] {final_result}") 
        
        # 임시 파일 정리
        temp_path = session_tempfiles.pop(sid, None)
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)
        
        print("세션 정리 완료.")