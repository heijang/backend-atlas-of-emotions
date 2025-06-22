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
import librosa

# Local application imports
from app.dao.user_conversation_dao import UserConversationDAO
from app.providers.gemini_client import analyze_emotions, analyze_conversation_emotions
from app.providers.stt_provider import get_streaming_stt_provider, get_sync_stt_provider
from app.utils.audio_utils import cut_wav_by_timestamps, get_storage_audio_path
from app.services.user_services import user_service
from app.services.user_voice_service import user_voice_service


class AnalyzeService:
    def __init__(self):
        self.user_conversation_dao = UserConversationDAO()

    async def handle_setup_message(self, sid: int, setup_data: dict, session_user_id: dict, user_voice_embeddings_mem: dict) -> tuple[dict, str | None]:
        event = setup_data.get("event")
        if event != "send_conversation":
            return {"status": "error", "message": f"Unknown event: {event}"}, None

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
        
        return {"event": "send_conversation", "status": "ok"}, user_id

    # 1. STT 처리 (I/O Bound)
    async def transcribe_chunk(self, chunk_bytes: bytes) -> str | None:
        print(f"[실시간 처리] STT 요청 시작")
        start_time = time.time()
        # I/O 작업인 STT 요청을 별도 스레드에서 실행
        transcript = await asyncio.to_thread(get_streaming_stt_provider().streaming, chunk_bytes)
        end_time = time.time()
        print(f"[실시간 처리] STT 소요 시간: {end_time - start_time:.4f}초. 결과: {transcript}")
        return transcript

    # 2. 오디오 처리 (CPU Bound)
    async def _process_audio_for_analysis(self, chunk_bytes: bytes):
        print(f"[실시간 처리] 오디오 처리 시작")
        start_time = time.time()
        def _process_audio_with_librosa(data):
            with io.BytesIO() as wav_io:
                with wave.open(wav_io, 'wb') as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(16000)
                    wf.writeframes(data)
                wav_io.seek(0)
                return librosa.load(wav_io, sr=16000, mono=True)
        
        # CPU 집약적인 작업을 별도 스레드에서 실행
        audio_array, _ = await asyncio.to_thread(_process_audio_with_librosa, chunk_bytes)
        end_time = time.time()
        print(f"[실시간 처리] 오디오 처리 소요 시간: {end_time - start_time:.4f}초")
        return audio_array

    # 3. 감정 분석 (I/O Bound)
    async def analyze_emotion_from_audio_and_text(self, transcript: str, audio_array) -> dict | None:
        print(f"[실시간 처리] Gemini 요청 시작")
        start_time = time.time()
        # I/O 작업인 Gemini API 요청을 별도 스레드에서 실행
        emotion_result = await asyncio.to_thread(analyze_emotions, transcript, audio_array)
        end_time = time.time()
        print(f"[실시간 처리] Gemini 감정 분석 소요 시간: {end_time - start_time:.4f}초")
        return emotion_result

    # 4. 음성 비교 (CPU/File I/O Bound)
    async def compare_voice_in_chunk(self, chunk_bytes: bytes, user_embedding: list) -> tuple[bool | None, float | None]:
        print(f"[실시간 처리] 음성 비교 시작")
        start_time = time.time()
        # 파일 I/O와 계산이 섞여 있으므로 스레드에서 실행
        is_same, similarity = await asyncio.to_thread(self._compare_voice_in_memory, chunk_bytes, user_embedding)
        end_time = time.time()
        print(f"[실시간 처리] 음성 유사도 분석 소요 시간: {end_time - start_time:.4f}초")
        return is_same, similarity

    def _compare_voice_in_memory(self, chunk_bytes: bytes, user_embedding: list) -> tuple[bool | None, float | None]:
        if user_embedding is None:
            return None, None
        
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_wav:
                with wave.open(temp_wav.name, 'wb') as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(16000)
                    wf.writeframes(chunk_bytes)
                temp_wav_path = temp_wav.name
            is_same, similarity = user_voice_service.compare_voice(temp_wav_path, user_embedding, threshold=0.5)
            return is_same, similarity
        except Exception as e:
            print(f"[실시간 음성 식별 에러] {e}")
            return None, None
        finally:
            if 'temp_wav_path' in locals() and os.path.exists(temp_wav_path):
                os.remove(temp_wav_path)

    def finalize_analysis(self, wav_path: str, full_audio_buffer: bytearray, user_id: str, sid: int, ts: str, user_voice_embeddings_mem: dict):
        if len(full_audio_buffer) == 0:
            print("후처리할 오디오 데이터가 없습니다.")
            return

        with wave.open(wav_path, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(full_audio_buffer)
        
        with open(wav_path, "rb") as f:
            full_audio = f.read()

        clova_start = time.time()
        print(f"[Clova 분석] 요청 시작: {clova_start}")
        final_result = get_sync_stt_provider().sync(full_audio)
        clova_end = time.time()
        print(f"[Clova 분석] 요청 종료: {clova_end}, 소요시간: {clova_end - clova_start:.2f}초")

        print(f"[최종 STT] {final_result}")

        # `final_result`가 없거나 'segments'가 비어있으면 처리를 중단합니다.
        if not final_result or not final_result.get("segments"):
            print("후처리할 STT 세그먼트가 없습니다.")
            return

        segments = final_result["segments"]

        print("[최종 STT - Clova diarization 결과]")
        user_uid = user_service.get_user_uid_by_user_id(user_id or "test_user")
        master_uid = self.user_conversation_dao.insert_conversation_master(user_uid, topic=None)
        print(f"[DB] user_conversation_master 저장: master_uid={master_uid}")

        user_embedding = user_voice_embeddings_mem.get(user_id)
        
        segment_timestamps = [(seg.get('start') / 1000, seg.get('end') / 1000) for seg in segments]
        segment_dir = get_storage_audio_path(f"segments/{ts}_{sid}")
        segment_files = cut_wav_by_timestamps(wav_path, segment_timestamps, segment_dir)
        print(f"[문장별 오디오 컷팅 경로] {segment_files}")

        # Gemini에 전달할 대화 세그먼트 리스트 생성
        conversation_for_gemini = []
        for i, seg in enumerate(segments):
            text = seg.get('text')
            if not text:
                continue
            
            seg_wav_path = segment_files[i] if i < len(segment_files) else wav_path
            try:
                audio_array, _ = librosa.load(seg_wav_path, sr=16000, mono=True)
                conversation_for_gemini.append({
                    "text": text,
                    "speaker": str(seg.get('speaker', {}).get('label')) if isinstance(seg.get('speaker'), dict) else str(seg.get('speaker')),
                    "audio": audio_array,
                })
            except Exception as e:
                print(f"오디오 파일 로드 실패 (Segment {i+1}): {e}")
                # 오디오 로드 실패 시, audio는 None으로 전달
                conversation_for_gemini.append({
                    "text": text,
                    "speaker": str(seg.get('speaker', {}).get('label')) if isinstance(seg.get('speaker'), dict) else str(seg.get('speaker')),
                    "audio": None,
                })

        # 전체 대화 맥락을 사용하여 감정 분석 (1회 호출)
        emotion_results_list = analyze_conversation_emotions(conversation_for_gemini)

        # 분석 결과와 원본 데이터를 조합하여 DB에 저장
        for i, seg in enumerate(segments):
            if i >= len(emotion_results_list): break

            emotion_result = emotion_results_list[i]
            sentence_text = seg.get('text')
            if not sentence_text: continue

            try:
                # 음성 유사도 분석은 개별적으로 수행
                seg_wav_path = segment_files[i] if i < len(segment_files) else wav_path
                is_same, similarity = user_voice_service.compare_voice(seg_wav_path, user_embedding, threshold=0.75)
                print(f"[음성 식별] Segment {i+1} | 유사도: {similarity:.4f} | 동일인: {is_same}")
                
                dominant_emotion = emotion_result.get('audio', {}).get('dominant', 'neutral')
                
                self.user_conversation_dao.insert_conversation_detail(
                    master_uid=master_uid,
                    sentence=sentence_text,
                    speaker=str(seg.get('speaker', {}).get('label')) if isinstance(seg.get('speaker'), dict) else str(seg.get('speaker')),
                    emotion_result=json.dumps(emotion_result, ensure_ascii=False),
                    dominant_emotion=dominant_emotion,
                    start_ms=seg.get('start'),
                    end_ms=seg.get('end')
                )
                print(f"[DB] user_conversation_detail 저장: master_uid={master_uid}, seg_idx={i}")

            except Exception as e:
                print(f"[최종 분석] Segment {i+1} 처리 중 에러: {e}")

        if master_uid:
            self.user_conversation_dao.update_master_audio_path(master_uid, wav_path)
            print(f"[DB] user_conversation_master.audio_path 업데이트: master_uid={master_uid}")
        
        self.user_conversation_dao.close()


analyze_service = AnalyzeService() 