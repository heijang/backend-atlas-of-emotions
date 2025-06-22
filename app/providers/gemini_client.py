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

def analyze_conversation_emotions(segments: list) -> list:
    """
    (신규) 전체 대화 세그먼트 리스트를 받아, 각 세그먼트의 텍스트와 음성을 종합적으로 분석합니다.
    하나의 프롬프트로 전체 대화의 맥락을 제공하여 Gemini가 더 정확하게 감정을 분석하도록 합니다.

    :param segments: [{'text': str, 'speaker': str, 'audio': np.ndarray}, ...]
    :return: 각 세그먼트에 대한 감정 분석 결과 dict의 리스트. analyze_emotions와 동일한 포맷.
    """
    if not model or not segments:
        # 모델이 없거나 세그먼트가 없으면 개별 분석으로 폴백
        return [analyze_emotions(seg.get('text', ''), seg.get('audio')) for seg in segments]

    temp_files_to_clean = []
    try:
        prompt_parts = [
            "You are an expert conversation analyst. Below is a transcript of a conversation with multiple speakers, including the audio for each segment. Your task is to analyze the emotion for EACH segment based on both the text and the audio, considering the overall context of the conversation.",
            "Analyze each segment and provide a response in a single JSON array format. Each object in the array should correspond to a segment and have the following structure:",
            '{"text_analysis": {"positive": float, "negative": float, "neutral": float}, "audio_analysis": {"happy": float, "sad": float, "angry": float, "fear": float, "disgust": float, "surprise": float, "neutral": float}}',
            "Ensure the sum of scores in each dictionary is 1.0. Here is the conversation data:"
        ]

        for i, seg in enumerate(segments):
            text = seg.get('text', '')
            speaker = seg.get('speaker', 'Unknown')
            audio_array = seg.get('audio')

            prompt_parts.append(f"\n--- Segment {i+1} ---\nSpeaker: {speaker}\nText: \"{text}\"")
            
            if audio_array is not None and audio_array.size > 0:
                temp_wav = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
                temp_files_to_clean.append(temp_wav.name)
                with wave.open(temp_wav.name, "wb") as wav_file:
                    wav_file.setnchannels(1)
                    wav_file.setsampwidth(2)
                    wav_file.setframerate(16000)
                    wav_data = (audio_array * 32767).astype(np.int16)
                    wav_file.writeframes(wav_data.tobytes())
                audio_file = genai.upload_file(path=temp_wav.name)
                prompt_parts.append(audio_file)

        print(f"[Gemini 대화 분석] {len(segments)}개 세그먼트 분석 요청 시작...")
        response = model.generate_content(prompt_parts, generation_config={"response_mime_type": "application/json"})
        
        analysis_results = json.loads(response.text)
        
        processed_results = []
        for res in analysis_results:
            text_scores = res.get("text_analysis", {"neutral": 1.0})
            audio_scores = res.get("audio_analysis", {"neutral": 1.0})
            
            text_dominant = get_dominant_emotion(text_scores)
            audio_dominant = get_dominant_emotion(audio_scores)

            # analyze_emotions와 동일한 포맷으로 결과 구성
            processed_results.append({
                "text": {
                    "scores": text_scores, "dominant": text_dominant,
                    "standard": map_emotion_to_standard(text_dominant),
                    "korean": map_emotion_to_korean(text_dominant),
                    "color": map_emotion_to_color(map_emotion_to_standard(text_dominant)),
                },
                "audio": {
                    "scores": audio_scores, "dominant": audio_dominant,
                    "standard": map_emotion_to_standard(audio_dominant),
                    "korean": map_emotion_to_korean(audio_dominant),
                    "color": map_emotion_to_color(map_emotion_to_standard(audio_dominant)),
                },
            })
        print(f"[Gemini 대화 분석] 분석 완료.")
        return processed_results

    except Exception as e:
        print(f"Error in Gemini conversation analysis: {e}")
        return [analyze_emotions(seg.get('text', ''), seg.get('audio')) for seg in segments]
    finally:
        # 모든 임시 오디오 파일 정리
        for f in temp_files_to_clean:
            if os.path.exists(f):
                try:
                    os.unlink(f)
                except OSError as e:
                    print(f"Error removing temp file {f}: {e}")

def analyze_emotions(text, audio_array):
    """
    단일 텍스트와 오디오를 입력받아 Gemini로 감정 분석을 수행합니다.
    (기존 함수는 이제 내부 헬퍼 함수들을 호출하는 래퍼 역할을 합니다)
    """
    text_scores = analyze_text_sentiment(text)
    audio_scores = analyze_audio_emotion(audio_array)
    return _format_analysis_result(text_scores, audio_scores)

def _format_analysis_result(text_scores, audio_scores):
    """
    텍스트 및 오디오 감정 분석 점수를 받아 최종 결과 dict 포맷으로 만듭니다.
    """
    text_dominant = get_dominant_emotion(text_scores)
    audio_dominant = get_dominant_emotion(audio_scores)
    
    return {
        "text": {
            "scores": text_scores,
            "dominant": text_dominant,
            "standard": map_emotion_to_standard(text_dominant),
            "korean": map_emotion_to_korean(text_dominant),
            "color": map_emotion_to_color(map_emotion_to_standard(text_dominant)),
        },
        "audio": {
            "scores": audio_scores,
            "dominant": audio_dominant,
            "standard": map_emotion_to_standard(audio_dominant),
            "korean": map_emotion_to_korean(audio_dominant),
            "color": map_emotion_to_color(map_emotion_to_standard(audio_dominant)),
        },
    }
