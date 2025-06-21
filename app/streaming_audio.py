import os
from datetime import datetime
from google.cloud import speech_v1p1beta1 as speech
from app.util.audio_utils import get_storage_audio_path
import tempfile
import subprocess
import wave
import queue
import threading
from collections import defaultdict
from dotenv import load_dotenv
from pathlib import Path

# --- 환경변수 로드 (.env) ---
dotenv_path = Path(__file__).parent.parent / "ENV" / ".env"
if dotenv_path.exists():
    load_dotenv(dotenv_path=dotenv_path)
# --------------------------

# =====================
# Google Cloud 인증 설정 (resources 폴더)
# =====================
GOOGLE_APPLICATION_CREDENTIALS = os.path.abspath(os.path.join(os.path.dirname(__file__), '../resources/service-account.json'))
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = GOOGLE_APPLICATION_CREDENTIALS
# =====================

# 환경 설정
AUDIO_DIR = get_storage_audio_path("stream_sessions")
os.makedirs(AUDIO_DIR, exist_ok=True)
WAV_DIR = get_storage_audio_path("wav_chunks")
os.makedirs(WAV_DIR, exist_ok=True)
SAMPLE_RATE = 16000
CHUNK_DURATION_SEC = 1.0  # 1초마다 STT
PCM_BYTES_PER_SEC = SAMPLE_RATE * 2  # 16bit(2byte) * 16000

# 세션별 파일/버퍼 관리
session_files = {}
session_buffers = {}
session_pcm_files = {}  # 세션별 임시 PCM 파일 경로 관리
session_queues = {}  # 세션별 STT 스트리밍용 큐
session_threads = {}  # 세션별 STT 스레드

# Google STT 클라이언트
speech_client = speech.SpeechClient()

# =====================
# STT Provider Abstraction
# =====================

class GoogleSTTProvider:
    def streaming(self, audio_bytes):
        return google_stt_streaming(audio_bytes)
    def sync(self, audio_bytes):
        return google_stt_sync(audio_bytes)

def get_clova_client():
    from app.clova_speech_client import ClovaSpeechClient
    return ClovaSpeechClient()

class ClovaSTTProvider:
    def __init__(self):
        self.client = get_clova_client()
    def streaming(self, audio_bytes):
        # Clova는 동기 방식만 지원하므로 streaming도 sync로 처리
        result = self.client.recognize(audio_bytes)
        if result and 'text' in result:
            return result['text']
        return ""
    def sync(self, audio_bytes):
        result = self.client.recognize(audio_bytes)
        # If diarization segments are present, print and return them
        if result and 'segments' in result:
            print('=== Clova diarization segments ===')
            segments = []
            for i, segment in enumerate(result['segments']):
                text = segment.get('text', '').strip()
                speaker_id = segment.get('speaker')
                start = segment.get('start')
                end = segment.get('end')
                print(f"[Segment {i+1}] Speaker: {speaker_id} | Start: {start} | End: {end} | Text: {text}")
                if text:
                    segments.append({'speaker': speaker_id, 'text': text, 'start': start, 'end': end})
            print(f"STT with diarization: {len(segments)} segments found.")
            return segments
        # Fallback: return text only
        if result and 'text' in result:
            return [{'speaker': None, 'text': result['text'], 'start': None, 'end': None}]
        return []

# 선택적으로 사용할 수 있도록 provider를 선택
STT_PROVIDERS = {
    'google': GoogleSTTProvider(),
    'clova': ClovaSTTProvider(),
}

# 기본 provider (환경변수 또는 코드에서 변경 가능)
def get_stt_provider():
    import os
    provider = os.getenv('STT_PROVIDER', 'clova')  # 기본값 clova
    return STT_PROVIDERS.get(provider, ClovaSTTProvider())

# chunk 단위 STT는 구글, 최종 STT는 클로바를 사용하도록 provider 분리

def get_streaming_stt_provider():
    return GoogleSTTProvider()

def get_sync_stt_provider():
    return ClovaSTTProvider()

# 연결 시 파일/버퍼 초기화
def start_streaming_session(sid):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    file_path = os.path.join(AUDIO_DIR, f"session_{ts}_{sid}.webm")
    session_files[sid] = file_path
    session_buffers[sid] = bytearray()
    pcm_path = os.path.join(WAV_DIR, f"session_{ts}_{sid}.pcm")
    session_pcm_files[sid] = pcm_path
    with open(pcm_path, "wb") as f:
        pass  # 파일 생성
    # STT 스트리밍용 큐/스레드 시작
    q = queue.Queue()
    session_queues[sid] = q
    t = threading.Thread(target=stt_streaming_worker, args=(sid, q), daemon=True)
    session_threads[sid] = t
    t.start()
    return file_path

# chunk 수신 시 파일에 append 및 버퍼에 저장
def handle_audio_chunk(sid, data):
    buffer = session_buffers.get(sid)
    pcm_path = session_pcm_files.get(sid)
    q = session_queues.get(sid)
    if buffer is not None and pcm_path is not None and q is not None:
        buffer.extend(data)
        with open(pcm_path, "ab") as f:
            f.write(data)
        # STT용 큐에 chunk를 넣음
        q.put(data)
        return None
    return None

# 세션 종료 시 전체 PCM을 WAV로 저장
def save_pcm_to_wav(pcm_bytes, wav_path, sample_rate=16000):
    with wave.open(wav_path, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16bit
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)

# 연결 해제 시 파일 경로 반환 및 정리
def end_streaming_session(sid):
    pcm_path = session_pcm_files.pop(sid, None)
    session_buffers.pop(sid, None)
    # STT 스트리밍 종료 신호
    q = session_queues.pop(sid, None)
    if q is not None:
        q.put(None)
    t = session_threads.pop(sid, None)
    # 전체 PCM을 WAV로 저장
    if pcm_path and os.path.exists(pcm_path):
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        wav_path = os.path.join(WAV_DIR, f"session_{ts}_{sid}.wav")
        with open(pcm_path, "rb") as f:
            pcm_bytes = f.read()
        save_pcm_to_wav(pcm_bytes, wav_path)
        os.remove(pcm_path)
        print(f"[서버] 전체 PCM을 WAV로 저장: {wav_path}")

        # === 전체 파일을 동기 STT로 전송 ===
        with open(wav_path, "rb") as f:
            wav_bytes = f.read()
        transcript = google_stt_sync(wav_bytes)
        print(f"[전체 파일 STT 결과] {transcript}")
        # =============================

        return wav_path
    session_files.pop(sid, None)
    return None

def google_stt_streaming(audio_bytes):
    config = speech.RecognitionConfig(
        encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
        sample_rate_hertz=16000,
        language_code="ko-KR",
    )
    streaming_config = speech.StreamingRecognitionConfig(
        config=config,
        interim_results=False,
        single_utterance=True,
    )
    if isinstance(audio_bytes, bytearray):
        audio_bytes = bytes(audio_bytes)
    def request_generator():
        yield speech.StreamingRecognizeRequest(audio_content=audio_bytes)
    try:
        responses = speech_client.streaming_recognize(streaming_config, request_generator())
        for response in responses:
            for result in response.results:
                if result.is_final and result.alternatives:
                    transcript = result.alternatives[0].transcript
                    print(f"[실시간 STT:streaming] {transcript}")
                    return transcript
    except Exception as e:
        print(f"[STT 에러] {e}")
    return ""

def google_stt_sync(audio_bytes):
    config = speech.RecognitionConfig(
        encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
        sample_rate_hertz=16000,
        language_code="ko-KR",
        alternative_language_codes=["en-US"],
        enable_speaker_diarization=True,
        diarization_speaker_count=2,
    )
    # bytearray → bytes 변환
    if isinstance(audio_bytes, bytearray):
        audio_bytes = bytes(audio_bytes)
    audio = speech.RecognitionAudio(content=audio_bytes)
    # LongRunningRecognize 사용
    operation = speech_client.long_running_recognize(config=config, audio=audio)
    response = operation.result(timeout=180)
    transcript = ""
    speaker_segments = defaultdict(str)
    for result in response.results:
        if result.alternatives:
            alternative = result.alternatives[0]
            transcript += alternative.transcript + "\n"
            # 화자별 단어 모으기 (speaker_tag=0은 무시)
            if hasattr(alternative, 'words'):
                for w in alternative.words:
                    if hasattr(w, 'speaker_tag') and w.speaker_tag and w.speaker_tag > 0:
                        speaker_segments[w.speaker_tag] += w.word + ' '
    for speaker, text in speaker_segments.items():
        print(f"[전체 파일 STT][화자 {speaker}] {text.strip()}")
    return transcript.strip()

def stt_streaming_worker(sid, q):
    config = speech.RecognitionConfig(
        encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
        sample_rate_hertz=16000,
        language_code="ko-KR",
        enable_word_time_offsets=True,  # 단어별 타임스탬프(문장 자르기 등 활용 가능)
        enable_speaker_diarization=True,  # 화자 구분 활성화
        diarization_speaker_count=2,      # 예상 화자 수(필요시 조정)
    )
    streaming_config = speech.StreamingRecognitionConfig(
        config=config,
        interim_results=True,  # 실시간 중간 결과도 받기
        single_utterance=False,
    )
    def request_generator():
        while True:
            chunk = q.get()
            if chunk is None:
                break
            if isinstance(chunk, bytearray):
                chunk = bytes(chunk)
            yield speech.StreamingRecognizeRequest(audio_content=chunk)
    try:
        responses = speech_client.streaming_recognize(streaming_config, request_generator())
        for response in responses:
            for result in response.results:
                if result.alternatives:
                    transcript = result.alternatives[0].transcript
                    if result.is_final:
                        # 화자별로 구분해서 출력
                        words = result.alternatives[0].words
                        if words:
                            last_speaker = None
                            speaker_text = ''
                            for w in words:
                                if last_speaker is None:
                                    last_speaker = w.speaker_tag
                                if w.speaker_tag != last_speaker:
                                    print(f"[STT:FINAL][화자 {last_speaker}] {speaker_text.strip()}")
                                    speaker_text = w.word + ' '
                                    last_speaker = w.speaker_tag
                                else:
                                    speaker_text += w.word + ' '
                            if speaker_text:
                                print(f"[STT:FINAL][화자 {last_speaker}] {speaker_text.strip()}")
                        else:
                            print(f"[실시간 STT:FINAL] {transcript}")
                    else:
                        print(f"[실시간 STT:INTERIM] {transcript}")
    except Exception as e:
        print(f"[STT 에러] {e}")

load_dotenv(dotenv_path=Path(__file__).parent.parent / "ENV" / ".env") 