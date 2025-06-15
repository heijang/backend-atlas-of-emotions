import os
from flask import Flask, render_template, session
from flask_socketio import SocketIO, emit
import google.generativeai as genai
import numpy as np
import json
import base64
import sounddevice as sd
import librosa
from dotenv import load_dotenv
from pathlib import Path
import wave
import io
import tempfile
from google.cloud import speech_v1
from google.api_core import client_options
from google.cloud.speech_v1 import SpeechClient
from google.auth import credentials
from google.oauth2 import service_account
from clova_speech_client import ClovaSpeechClient
import csv
from datetime import datetime
import pytz
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.preprocessing import normalize

# Build a path to the .env file from the script's location for robust loading
dotenv_path = Path(__file__).parent / ".env"
if dotenv_path.exists():
    print(f"Loading .env file from: {dotenv_path}")
    load_dotenv(dotenv_path=dotenv_path)
else:
    print(
        f"Warning: .env file not found at {dotenv_path}. Environment variables may not be loaded."
    )

print("--- .env file loading status ---")
print(f"CLOVA_SPEECH_INVOKE_URL: {os.getenv('CLOVA_SPEECH_INVOKE_URL')}")
print(f"CLOVA_SPEECH_API_KEY: {os.getenv('CLOVA_SPEECH_API_KEY')}")
print(f"GOOGLE_API_KEY: {'Loaded' if os.getenv('GOOGLE_API_KEY') else 'Not Loaded'}")
print("---------------------------------")

# Initialize Flask app
app = Flask(__name__)
app.config["SECRET_KEY"] = "your-secret-key"
# Increase buffer size to handle larger audio chunks
socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    max_http_buffer_size=100000000,  # 100MB buffer size
    ping_timeout=60,  # Increase ping timeout
    ping_interval=25,  # Default ping interval
    async_mode="threading",  # Use threading mode instead of eventlet
)

# Configure API Key
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if not GOOGLE_API_KEY:
    raise ValueError("GOOGLE_API_KEY not found in environment variables")

# (변경) Naver Clova Speech API Keys
CLOVA_SPEECH_INVOKE_URL = os.getenv("CLOVA_INVOKE_URL")
CLOVA_SPEECH_API_KEY = os.getenv("CLOVA_SECRET_KEY")

if not CLOVA_SPEECH_INVOKE_URL or not CLOVA_SPEECH_API_KEY:
    print(
        "Warning: CLOVA_SPEECH_INVOKE_URL or CLOVA_SPEECH_API_KEY not found. STT/Diarization will not work."
    )

# Configure Speech-to-Text client - This will be replaced by Clova client
speech_client = None
speech_v2_client = None
print("Google Speech-to-Text client is disabled. Using Naver Clova Speech.")

# Initialize Gemini model
try:
    # Configure Gemini API
    print("Configuring Gemini API...")
    genai.configure(api_key=GOOGLE_API_KEY)

    # Initialize the model
    print("Initializing Gemini model (gemini-2.0-flash)...")
    model = genai.GenerativeModel("gemini-2.0-flash")

    # Test the model to ensure it's working
    print("Testing Gemini model...")
    test_response = model.generate_content("Hello")
    print("Gemini model test successful. Response:", test_response.text.strip())

except Exception as e:
    print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
    print("!!! CRITICAL: Failed to initialize Gemini model        !!!")
    print(f"!!! Error: {str(e)}")
    print("!!! Sentiment analysis will NOT work.                !!!")
    print("!!! Please check your GOOGLE_API_KEY and API permissions. !!!")
    print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
    model = None

# Emotion colors mapping
EMOTION_COLORS = {
    "positive": "#FFD700",  # Gold
    "negative": "#4682B4",  # Steel Blue
    "angry": "#FF4500",  # Red Orange
    "fear": "#800080",  # Purple
    "disgust": "#006400",  # Dark Green
    "surprise": "#FF69B4",  # Hot Pink
    "neutral": "#F5F5F5",  # Light Gray
    "happy": "#FFD700",  # Alias for positive
    "sad": "#4682B4",  # Alias for negative
}

EMOTION_MAPPING = {
    "positive": "긍정",
    "negative": "부정",
    "neutral": "중립",
    "happy": "행복",
    "sad": "슬픔",
    "angry": "분노",
    "fear": "두려움",
    "disgust": "혐오",
    "surprise": "놀람",
}

# 7가지 세분된 감정을 3가지 대표 감정으로 표준화하기 위한 맵
EMOTION_MAP = {
    "positive": "positive",
    "negative": "negative",
    "neutral": "neutral",
    "happy": "positive",
    "surprise": "positive",
    "sad": "negative",
    "angry": "negative",
    "fear": "negative",
    "disgust": "negative",
}

# 로깅 설정
KST = pytz.timezone("Asia/Seoul")
OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)

# 세션별 로깅 상태 추적
logging_sessions = {}
session_log_files = {}  # 세션별 로그 파일명 저장

# 화자 인식을 위한 설정
SPEAKER_LABEL_DIR = Path("speaker_label")
reference_speaker_embedding = None  # 참조 화자(나)의 임베딩
SIMILARITY_THRESHOLD = 0.98  # 화자 인식 임계값


def get_session_log_filename(session_id):
    """세션별로 고유한 로그 파일명 생성 (밀리초 포함)"""
    if session_id not in session_log_files:
        now = datetime.now(KST)
        timestamp = now.strftime("%Y%m%d_%H%M%S_%f")[:-3]  # 밀리초까지만
        filename = f"emotion_analysis_{timestamp}.txt"
        session_log_files[session_id] = OUTPUT_DIR / filename
    return session_log_files[session_id]


def get_korean_timestamp():
    """한국시간 타임스탬프 반환"""
    return datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")


def write_log_entry(speaker, text, text_emotion, audio_emotion, session_id=None):
    """로그 엔트리를 CSV 형태로 파일에 기록"""
    try:
        log_file = (
            get_session_log_filename(session_id)
            if session_id
            else OUTPUT_DIR / "default.txt"
        )
        timestamp = get_korean_timestamp()

        # 텍스트 감정 분석 결과를 JSON 문자열로 변환
        text_emotion_str = json.dumps(text_emotion, ensure_ascii=False)

        # 텍스트 감정 중 가장 높은 것 선택 (안전하게 처리)
        if text_emotion and isinstance(text_emotion, dict):
            # 값을 float로 변환하여 비교
            emotion_values = {}
            for key, value in text_emotion.items():
                try:
                    emotion_values[key] = float(value)
                except (ValueError, TypeError):
                    emotion_values[key] = 0.0
            text_dominant = max(
                emotion_values, key=emotion_values.get, default="neutral"
            )
        else:
            text_dominant = "neutral"

        text_dominant_korean = {
            "positive": "긍정",
            "negative": "부정",
            "neutral": "중립",
        }.get(text_dominant, "중립")

        # 오디오 감정 분석 결과를 JSON 문자열로 변환
        audio_emotion_str = json.dumps(audio_emotion, ensure_ascii=False)

        # 오디오 감정 중 가장 높은 것 선택 (안전하게 처리)
        if audio_emotion and isinstance(audio_emotion, dict):
            # 값을 float로 변환하여 비교
            emotion_values = {}
            for key, value in audio_emotion.items():
                try:
                    emotion_values[key] = float(value)
                except (ValueError, TypeError):
                    emotion_values[key] = 0.0
            audio_dominant = max(
                emotion_values, key=emotion_values.get, default="neutral"
            )
        else:
            audio_dominant = "neutral"

        audio_dominant_korean = {
            "happy": "행복",
            "sad": "슬픔",
            "angry": "분노",
            "fear": "두려움",
            "disgust": "혐오",
            "surprise": "놀람",
            "neutral": "중립",
        }.get(audio_dominant, "중립")

        # 파이프라인으로 구분된 로그 라인 생성
        # 형식: 한국타임스탬프|화자라벨링번호|텍스트내용|텍스트감정JSON|텍스트감정(우세한것)|오디오감정JSON|오디오감정(우세한것)
        safe_text = text.replace("|", "｜")  # 파이프라인을 전각 파이프로 변환
        log_line = f"{timestamp}|{speaker}|{safe_text}|{text_emotion_str}|{text_dominant_korean}|{audio_emotion_str}|{audio_dominant_korean}\n"

        with open(log_file, "a", encoding="utf-8") as f:
            f.write(log_line)

        print(f"Log entry written to {log_file}: {text[:30]}...")

    except Exception as e:
        print(f"Error writing log entry: {str(e)}")
        import traceback

        traceback.print_exc()


def start_logging_session(session_id):
    """로깅 세션 시작 기록"""
    try:
        log_file = get_session_log_filename(session_id)
        timestamp = get_korean_timestamp()

        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"{timestamp}|SYSTEM|start log|||||\n")

        logging_sessions[session_id] = True
        print(f"Logging session started for {session_id}, file: {log_file}")

    except Exception as e:
        print(f"Error starting logging session: {str(e)}")


def end_logging_session(session_id):
    """로깅 세션 종료 기록"""
    try:
        if session_id in logging_sessions:
            log_file = get_session_log_filename(session_id)
            timestamp = get_korean_timestamp()

            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"{timestamp}|SYSTEM|end log|||||\n")

            del logging_sessions[session_id]
            # 세션 종료 시 로그 파일 정보도 정리
            if session_id in session_log_files:
                print(
                    f"Logging session ended for {session_id}, file: {session_log_files[session_id]}"
                )
                del session_log_files[session_id]

    except Exception as e:
        print(f"Error ending logging session: {str(e)}")


def extract_audio_features(audio_array, sample_rate=16000):
    """오디오에서 MFCC 특성을 추출"""
    try:
        # MFCC 특성 추출
        mfccs = librosa.feature.mfcc(y=audio_array, sr=sample_rate, n_mfcc=13)
        # 시간축을 따라 평균 계산하여 고정 크기 벡터로 만들기
        mfcc_mean = np.mean(mfccs, axis=1)

        # 추가 특성들
        spectral_centroids = librosa.feature.spectral_centroid(
            y=audio_array, sr=sample_rate
        )
        spectral_mean = np.mean(spectral_centroids)

        zero_crossings = librosa.feature.zero_crossing_rate(y=audio_array)
        zcr_mean = np.mean(zero_crossings)

        # 모든 특성을 하나의 벡터로 결합
        features = np.concatenate([mfcc_mean, [spectral_mean, zcr_mean]])

        return features
    except Exception as e:
        print(f"Error extracting audio features: {str(e)}")
        return np.zeros(15)  # 기본값 반환


def load_reference_speaker():
    """참조 화자(나)의 음성 파일을 로드하고 임베딩 생성"""
    global reference_speaker_embedding

    try:
        reference_file = SPEAKER_LABEL_DIR / "me_audio.wav"
        if not reference_file.exists():
            print(f"Warning: Reference speaker file not found at {reference_file}")
            return False

        # 참조 음성 파일 로드
        audio_data, sample_rate = librosa.load(reference_file, sr=16000, mono=True)

        # 최소 길이 확인 (너무 짧으면 특성 추출이 어려움)
        if len(audio_data) < 1600:  # 0.1초 미만
            print("Warning: Reference audio too short")
            return False

        # 특성 추출
        reference_speaker_embedding = extract_audio_features(audio_data, 16000)

        print(
            f"Reference speaker embedding loaded successfully. Shape: {reference_speaker_embedding.shape}"
        )
        return True

    except Exception as e:
        print(f"Error loading reference speaker: {str(e)}")
        return False


def identify_speaker(audio_array):
    """음성을 분석하여 화자가 참조 화자(나)인지 판단"""
    global reference_speaker_embedding

    try:
        # 참조 임베딩이 없으면 로드 시도
        if reference_speaker_embedding is None:
            if not load_reference_speaker():
                # 참조 데이터가 없으면 기본 화자 구분 로직 사용
                return "2"  # 기본값으로 화자2 반환

        # 현재 오디오에서 특성 추출
        current_features = extract_audio_features(audio_array, 16000)

        # 코사인 유사도 계산
        ref_normalized = normalize([reference_speaker_embedding])
        curr_normalized = normalize([current_features])
        similarity = cosine_similarity(ref_normalized, curr_normalized)[0][0]

        print(
            f"Speaker similarity: {similarity:.3f} (threshold: {SIMILARITY_THRESHOLD})"
        )

        # 임계값보다 높으면 화자1(나), 낮으면 화자2
        if similarity > SIMILARITY_THRESHOLD:
            return "1"  # 나
        else:
            return "2"  # 다른 사람

    except Exception as e:
        print(f"Error in speaker identification: {str(e)}")
        return "2"  # 오류 시 기본값


@app.route("/")
def index():
    return render_template("index.html")


@socketio.on("start_stream")
def handle_start_stream(data):
    sample_rate = data.get("sampleRate", 44100)
    session["sample_rate"] = sample_rate
    session["emotion_scores"] = {"positive": 0, "negative": 0, "neutral": 0}

    # 로깅 세션 시작
    session_id = session.get("session_id", id(session))
    session["session_id"] = session_id
    start_logging_session(session_id)

    print(f"Client connected, sample rate: {sample_rate}, session: {session_id}")


@socketio.on("audio_data")
def handle_audio_data(data):
    try:
        sample_rate = session.get("sample_rate", 44100)  # 세션에서 샘플링 속도 가져오기

        # Remove the data URL prefix
        if "," in data:
            audio_data_base64 = data.split(",")[1]
        else:
            audio_data_base64 = data

        # Decode base64 to bytes
        audio_bytes = base64.b64decode(audio_data_base64)

        # Convert to numpy array with proper dtype
        audio_array_float32 = np.frombuffer(audio_bytes, dtype=np.float32)

        # Debug log
        print(
            f"Received audio data - Shape: {audio_array_float32.shape}, Min: {np.min(audio_array_float32)}, Max: {np.max(audio_array_float32)}"
        )

        # Ensure the array is not empty and has the correct shape
        if audio_array_float32.size == 0:
            raise ValueError("Empty audio data received")

        # Ensure the audio data is finite
        if not np.all(np.isfinite(audio_array_float32)):
            print("Warning: Non-finite values found in audio data")
            audio_array_float32 = np.nan_to_num(audio_array_float32)

        # Normalize audio data if needed
        if np.abs(audio_array_float32).max() > 1.0:
            print("Normalizing audio data")
            audio_array_float32 = (
                audio_array_float32 / np.abs(audio_array_float32).max()
            )

        # Check if audio is too quiet
        rms = np.sqrt(np.mean(np.square(audio_array_float32)))
        print(f"Audio RMS level: {rms}")
        if rms < 0.01:  # Arbitrary threshold, adjust if needed
            print("Warning: Audio signal is very quiet")
            return

        # 16kHz로 리샘플링
        audio_resampled = librosa.resample(
            y=audio_array_float32, orig_sr=sample_rate, target_sr=16000
        )

        rms = np.sqrt(np.mean(np.square(audio_resampled)))
        if rms < 0.01:
            # 너무 조용한 오디오는 무시
            return

        print(
            f"Received audio: {len(audio_array_float32)} samples at {sample_rate}Hz. Resampled to {len(audio_resampled)} samples at 16000Hz. RMS: {rms:.4f}"
        )

        # STT now returns a list of segments with speaker info
        segments = audio_to_text(audio_resampled)
        if not segments:
            return

        # Analyze audio emotion once for the entire chunk
        audio_emotion_scores = analyze_audio_emotion(audio_resampled)
        dominant_audio_emotion = max(
            audio_emotion_scores, key=audio_emotion_scores.get, default="neutral"
        )
        std_audio_emotion = EMOTION_MAP.get(dominant_audio_emotion, "neutral")

        print(f"Audio emotion analysis:")
        print(f"  Raw scores: {audio_emotion_scores}")
        print(f"  Dominant emotion: {dominant_audio_emotion}")
        print(
            f"  Mapped to Korean: {EMOTION_MAPPING.get(dominant_audio_emotion, '중립')}"
        )

        # Process each speaker segment
        for segment in segments:
            text = segment.get("text")
            speaker_id = segment.get("speaker")
            if not text:
                continue

            text_sentiment = analyze_text_sentiment(text)
            dominant_text_emotion = max(
                text_sentiment, key=text_sentiment.get, default="neutral"
            )
            std_text_emotion = EMOTION_MAP.get(dominant_text_emotion, "neutral")

            scores = session.get(
                "emotion_scores", {"positive": 0, "negative": 0, "neutral": 0}
            )
            scores[std_text_emotion] += 1
            scores[std_audio_emotion] += 1
            session["emotion_scores"] = scores

            cumulative_dominant_emotion = max(scores, key=scores.get)

            response = {
                "text": text,
                "speaker_id": speaker_id,
                "text_emotion": EMOTION_MAPPING.get(dominant_text_emotion, "중립"),
                "audio_emotion": EMOTION_MAPPING.get(dominant_audio_emotion, "중립"),
                "background_color": EMOTION_COLORS.get(
                    cumulative_dominant_emotion, "#F5F5F5"
                ),
            }

            # 로그 기록 (실시간 마이크 입력)
            session_id = session.get("session_id")
            if session_id and session_id in logging_sessions:
                write_log_entry(
                    speaker=speaker_id,
                    text=text,
                    text_emotion=text_sentiment,
                    audio_emotion=audio_emotion_scores,
                    session_id=session_id,
                )

            emit("analysis_result", response)

    except Exception as e:
        print(f"Error processing audio: {e}")
        emit("error", {"message": str(e)})


def analyze_speakers(audio_array):
    """
    참조 음성 파일을 기반으로 화자를 식별합니다.
    화자1(나) vs 화자2(다른 사람)로 구분
    """
    speaker_id = identify_speaker(audio_array)
    return {"speaker": speaker_id}


def audio_to_text(audio_array):
    """
    Transcribes audio using Naver Clova Speech API and returns speaker-separated segments.
    """
    if not CLOVA_SPEECH_API_KEY or not CLOVA_SPEECH_INVOKE_URL:
        print("Clova API credentials not configured. Skipping STT.")
        return []

    try:
        # Convert float32 audio array to 16-bit PCM WAV bytes
        audio_int16 = (audio_array * 32767).astype(np.int16)

        with io.BytesIO() as wav_io:
            with wave.open(wav_io, "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)  # 16-bit
                wav_file.setframerate(16000)
                wav_file.writeframes(audio_int16.tobytes())
            wav_bytes = wav_io.getvalue()

        # Initialize Clova client and send request
        clova_client = ClovaSpeechClient()
        result = clova_client.recognize(wav_bytes)

        if not result or "segments" not in result:
            print("Clova STT returned no segments.")
            return []

        # Parse the result from Clova into the application's expected format
        parsed_segments = []
        for segment in result["segments"]:
            # Clova의 화자 구분은 참고용으로만 사용하고, 우리의 화자 인식을 우선 적용
            text = segment.get("text", "").strip()
            if text:
                # 전체 오디오에서 화자 식별 (간단한 구현)
                speaker_id = identify_speaker(audio_array)
                parsed_segments.append({"speaker": speaker_id, "text": text})

        # 만약 Clova에서 세그먼트를 찾지 못했지만 텍스트가 있다면
        if not parsed_segments and len(audio_array) > 1600:  # 0.1초 이상
            # 전체 오디오에 대해 간단한 STT 시도 (fallback)
            speaker_id = identify_speaker(audio_array)
            # 이 경우 텍스트는 없지만 화자 정보는 제공
            parsed_segments.append({"speaker": speaker_id, "text": ""})

        print(
            f"STT with speaker identification successful: {len(parsed_segments)} segments found."
        )
        return parsed_segments

    except Exception as e:
        print(f"Error in audio_to_text (Clova integration): {e}")
        import traceback

        traceback.print_exc()
        return []


def analyze_text_sentiment(text):
    if not model:
        print("Model not initialized, returning default sentiment")
        return {"positive": 0.33, "negative": 0.33, "neutral": 0.34}

    try:
        # Simplified prompt for better reliability
        prompt = f"""Analyze the sentiment of this text: "{text}"
Return only a JSON object with this exact format:
{{"positive": number between 0 and 1, "negative": number between 0 and 1, "neutral": number between 0 and 1}}
The sum of all numbers should be 1."""

        response = model.generate_content(prompt)

        # Print the raw response for debugging
        print(f"Raw Gemini response: {response.text}")

        # Clean the response text
        response_text = response.text.strip()
        if response_text.startswith("```") and response_text.endswith("```"):
            response_text = response_text[3:-3]
        if response_text.startswith("json"):
            response_text = response_text[4:]
        response_text = response_text.strip()

        try:
            sentiment_scores = json.loads(response_text)
            # Validate the scores
            if not all(isinstance(v, (int, float)) for v in sentiment_scores.values()):
                print("Invalid score types, using default")
                return {"positive": 0.33, "negative": 0.33, "neutral": 0.34}

            total = sum(sentiment_scores.values())
            if abs(total - 1.0) > 0.1:  # Allow small deviation from 1.0
                print(f"Invalid sentiment scores (sum = {total}), using default")
                return {"positive": 0.33, "negative": 0.33, "neutral": 0.34}

            # Ensure all required keys are present
            required_keys = {"positive", "negative", "neutral"}
            if not all(key in sentiment_scores for key in required_keys):
                print("Missing required sentiment keys, using default")
                return {"positive": 0.33, "negative": 0.33, "neutral": 0.34}

            return sentiment_scores

        except json.JSONDecodeError as e:
            print(f"Error parsing JSON from response: {response_text}")
            print(f"JSON error: {str(e)}")
            return {"positive": 0.33, "negative": 0.33, "neutral": 0.34}

    except Exception as e:
        print(f"Error analyzing text sentiment: {str(e)}")
        return {"positive": 0.33, "negative": 0.33, "neutral": 0.34}


def analyze_audio_emotion(audio_array):
    if model is None:
        return {"neutral": 1.0}

    temp_wav_name = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_wav:
            with wave.open(temp_wav.name, "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)  # 16-bit
                wav_file.setframerate(16000)
                wav_data = (audio_array * 32767).astype(np.int16)
                wav_file.writeframes(wav_data.tobytes())
            temp_wav_name = temp_wav.name

        audio_file = genai.upload_file(path=temp_wav_name)

        prompt = """
        Please analyze the emotion from the speaker's voice in the provided audio file. 
        Consider vocal cues like tone, pitch, and speed.
        Classify the emotion into one of the following 7 categories: 
        happy, sad, angry, fear, disgust, surprise, neutral.
        Respond ONLY with a valid JSON object where keys are these 7 emotions 
        and values are their confidence scores from 0.0 to 1.0, summing to 1.0.
        """

        response = model.generate_content(
            [prompt, audio_file],
            generation_config={"response_mime_type": "application/json"},
        )

        os.unlink(temp_wav_name)
        return json.loads(response.text)

    except Exception as e:
        print(f"Error in Gemini audio emotion analysis: {str(e)}")
        if temp_wav_name and os.path.exists(temp_wav_name):
            os.unlink(temp_wav_name)
        return {"neutral": 1.0}


@socketio.on("upload_file")
def handle_file_upload(data):
    """Enhanced file upload handler with multiple transcription strategies"""
    try:
        if "audio" not in data:
            emit("error", {"message": "No audio data provided"})
            return

        # Decode the uploaded file
        audio_data_base64 = data["audio"]
        if "," in audio_data_base64:
            audio_data_base64 = audio_data_base64.split(",")[1]

        audio_bytes = base64.b64decode(audio_data_base64)
        print(f"Uploaded file size: {len(audio_bytes)} bytes")

        # Process with Web Audio API - decode the uploaded file
        try:
            # Save to temporary file for processing
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
                temp_file.write(audio_bytes)
                temp_path = temp_file.name

            # Load and resample the audio
            audio_array, sample_rate = librosa.load(temp_path, sr=16000, mono=True)
            os.unlink(temp_path)  # Clean up

            print(
                f"Loaded audio: {len(audio_array)} samples, duration: {len(audio_array)/16000:.2f}s"
            )

            # Apply the enhanced transcription strategies
            segments = audio_to_text(audio_array)

            if not segments:
                emit(
                    "error",
                    {
                        "message": "전사에 실패했습니다. 다른 오디오 파일을 시도해보세요."
                    },
                )
                return

            print(f"Transcription successful: {len(segments)} segments found")

            # Process each segment for sentiment analysis
            all_emotions = []
            all_text_emotions = []

            for segment in segments:
                # Text sentiment analysis
                text_sentiment = analyze_text_sentiment(segment["text"])
                all_text_emotions.append(text_sentiment)

                # For uploaded files, we don't have raw audio per segment
                # So we'll use text-based emotion as proxy for audio emotion
                audio_emotion = text_sentiment  # Fallback to text-based
                all_emotions.append(audio_emotion)

            # Calculate cumulative emotions
            cumulative_text_emotion = {}
            cumulative_audio_emotion = {}

            for emotion_type in ["positive", "negative", "neutral"]:
                cumulative_text_emotion[emotion_type] = np.mean(
                    [emotion.get(emotion_type, 0) for emotion in all_text_emotions]
                )
                cumulative_audio_emotion[emotion_type] = np.mean(
                    [emotion.get(emotion_type, 0) for emotion in all_emotions]
                )

            # Determine dominant emotions
            dominant_text = max(
                cumulative_text_emotion, key=cumulative_text_emotion.get
            )
            dominant_audio = max(
                cumulative_audio_emotion, key=cumulative_audio_emotion.get
            )

            # 파일 업로드 결과 로깅
            session_id = session.get("session_id", "file_upload_session")
            session["session_id"] = session_id

            # 파일 업로드 세션 시작 (세션이 없는 경우)
            if session_id not in logging_sessions:
                start_logging_session(session_id)

            # 각 세그먼트 로깅
            for i, seg in enumerate(segments):
                write_log_entry(
                    speaker=seg["speaker"],
                    text=seg["text"],
                    text_emotion=all_text_emotions[i],
                    audio_emotion=all_emotions[i],
                    session_id=session_id,
                )

            # Create response with enhanced speaker information
            response = {
                "transcript": " ".join([seg["text"] for seg in segments]),
                "segments": [
                    {
                        "speaker": seg["speaker"],
                        "text": seg["text"],
                        "text_emotion": all_text_emotions[i],
                        "audio_emotion": all_emotions[i],
                        "timestamp": f"Segment {i+1}",
                    }
                    for i, seg in enumerate(segments)
                ],
                "text_emotion": cumulative_text_emotion,
                "audio_emotion": cumulative_audio_emotion,
                "cumulative_emotions": {
                    "text": cumulative_text_emotion,
                    "audio": cumulative_audio_emotion,
                    "dominant_text": dominant_text,
                    "dominant_audio": dominant_audio,
                },
                "background_color": EMOTION_COLORS.get(dominant_text, "#F5F5F5"),
                "upload_success": True,
                "total_speakers": len(set(seg["speaker"] for seg in segments)),
                "total_segments": len(segments),
            }

            emit("file_upload_result", response)

        except Exception as processing_error:
            print(f"Error processing uploaded file: {processing_error}")
            emit(
                "error", {"message": f"파일 처리 중 오류 발생: {str(processing_error)}"}
            )

    except Exception as e:
        print(f"Error in file upload handler: {e}")
        emit("error", {"message": f"파일 업로드 중 오류 발생: {str(e)}"})


@socketio.on("stop_recording")
def handle_stop_recording():
    """녹음 중지 시 로깅 세션 종료"""
    session_id = session.get("session_id")
    if session_id:
        end_logging_session(session_id)
        print(f"Recording stopped, session: {session_id}")


@socketio.on("disconnect")
def handle_disconnect():
    """클라이언트 연결 해제 시 로깅 세션 종료"""
    session_id = session.get("session_id")
    if session_id:
        end_logging_session(session_id)
        print(f"Client disconnected, session: {session_id}")


if __name__ == "__main__":
    # 애플리케이션 시작 시 참조 화자 로드
    print("Loading reference speaker...")
    if load_reference_speaker():
        print("✅ Reference speaker loaded successfully!")
        print(
            f"👤 Speaker 1 will be identified as 'YOU' based on {SPEAKER_LABEL_DIR}/me_audio.wav"
        )
        print(f"👥 All other speakers will be identified as 'Speaker 2'")
    else:
        print("⚠️  Warning: Could not load reference speaker")
        print(f"📁 Please ensure {SPEAKER_LABEL_DIR}/me_audio.wav exists")
        print("🔄 Using fallback speaker identification")

    ssl_context = ("cert.pem", "key.pem")
    socketio.run(
        app,
        debug=True,
        host="0.0.0.0",
        port=8000,
        allow_unsafe_werkzeug=True,
        ssl_context=ssl_context,
    )
