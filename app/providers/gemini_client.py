import os
import google.generativeai as genai
import numpy as np
import json
import tempfile
import wave
from dotenv import load_dotenv
from pathlib import Path

# .env 환경변수 로드 (상위 ENV 폴더 기준)
dotenv_path = Path(__file__).parent.parent.parent / "ENV" / ".env"
if dotenv_path.exists():
    load_dotenv(dotenv_path=dotenv_path)

# Gemini API Key
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if not GOOGLE_API_KEY:
    raise ValueError("GOOGLE_API_KEY not found in environment variables")

genai.configure(api_key=GOOGLE_API_KEY)

# Gemini 모델 초기화
def get_gemini_model():
    try:
        model = genai.GenerativeModel("gemini-1.5-flash")
        # 테스트 호출 (옵션)
        _ = model.generate_content("Hello")
        return model
    except Exception as e:
        print(f"[emotion_analyzer] Gemini 모델 초기화 실패: {e}")
        return None

model = get_gemini_model()

# 감정 색상, 한글 매핑, 표준화 맵
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

def get_dominant_emotion(emotion_scores: dict, default="neutral"):
    """
    감정 점수 dict에서 가장 높은 감정 key를 반환 (값이 없거나 dict가 아니면 default)
    """
    if emotion_scores and isinstance(emotion_scores, dict):
        try:
            emotion_values = {k: float(v) for k, v in emotion_scores.items()}
            return max(emotion_values, key=emotion_values.get, default=default)
        except Exception:
            return default
    return default

def map_emotion_to_standard(emotion: str) -> str:
    """7가지 감정을 3가지 표준 감정(positive/negative/neutral)으로 매핑"""
    return EMOTION_MAP.get(emotion, "neutral")

def map_emotion_to_korean(emotion: str) -> str:
    """영문 감정명을 한글로 매핑"""
    return EMOTION_MAPPING.get(emotion, "중립")

def map_emotion_to_color(emotion: str) -> str:
    """감정명에 해당하는 색상 hex코드 반환"""
    return EMOTION_COLORS.get(emotion, "#F5F5F5")

# 텍스트 감정 분석 함수
def analyze_text_sentiment(text):
    if not model:
        print("Model not initialized, returning default sentiment")
        return {"positive": 0.33, "negative": 0.33, "neutral": 0.34}
    try:
        prompt = f"""Analyze the sentiment of this text: \"{text}\"\nReturn only a JSON object with this exact format:\n{{\"positive\": number between 0 and 1, \"negative\": number between 0 and 1, \"neutral\": number between 0 and 1}}\nThe sum of all numbers should be 1."""
        response = model.generate_content(prompt)
        response_text = response.text.strip()
        if response_text.startswith("```") and response_text.endswith("```"):
            response_text = response_text[3:-3]
        if response_text.startswith("json"):
            response_text = response_text[4:]
        response_text = response_text.strip()
        try:
            sentiment_scores = json.loads(response_text)
            if not all(isinstance(v, (int, float)) for v in sentiment_scores.values()):
                return {"positive": 0.33, "negative": 0.33, "neutral": 0.34}
            total = sum(sentiment_scores.values())
            if abs(total - 1.0) > 0.1:
                return {"positive": 0.33, "negative": 0.33, "neutral": 0.34}
            required_keys = {"positive", "negative", "neutral"}
            if not all(key in sentiment_scores for key in required_keys):
                return {"positive": 0.33, "negative": 0.33, "neutral": 0.34}
            return sentiment_scores
        except json.JSONDecodeError:
            return {"positive": 0.33, "negative": 0.33, "neutral": 0.34}
    except Exception as e:
        print(f"Error analyzing text sentiment: {str(e)}")
        return {"positive": 0.33, "negative": 0.33, "neutral": 0.34}

# 음성 감정 분석 함수
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

def analyze_emotions(text, audio_array):
    """
    텍스트와 오디오를 입력받아 Gemini로 감정 분석을 수행하고,
    각 감정별 점수, 우세 감정, 표준 감정, 한글, 색상까지 포함한 dict를 반환합니다.
    """
    # 텍스트 감정 분석
    text_scores = analyze_text_sentiment(text)
    text_dominant = get_dominant_emotion(text_scores)
    text_std = map_emotion_to_standard(text_dominant)
    text_kor = map_emotion_to_korean(text_dominant)
    text_color = map_emotion_to_color(text_std)

    # 오디오 감정 분석
    audio_scores = analyze_audio_emotion(audio_array)
    audio_dominant = get_dominant_emotion(audio_scores)
    audio_std = map_emotion_to_standard(audio_dominant)
    audio_kor = map_emotion_to_korean(audio_dominant)
    audio_color = map_emotion_to_color(audio_std)

    # 최종 결과 dict
    return {
        "text": {
            "scores": text_scores,
            "dominant": text_dominant,
            "standard": text_std,
            "korean": text_kor,
            "color": text_color,
        },
        "audio": {
            "scores": audio_scores,
            "dominant": audio_dominant,
            "standard": audio_std,
            "korean": audio_kor,
            "color": audio_color,
        },
    }
