import requests
import json
import os
from dotenv import load_dotenv
from pathlib import Path

# 프로젝트 루트를 기준으로 ENV/.env 파일의 절대 경로를 계산하여 환경 변수를 로드합니다.
project_root = Path(__file__).resolve().parents[2]
env_path = project_root / 'ENV' / '.env'
load_dotenv(dotenv_path=env_path)


class ClovaSpeechClient:
    """
    Naver Clova Speech API client for both long and short speech recognition.
    """

    def __init__(self):
        # Long-form API credentials
        self.long_invoke_url = os.getenv("CLOVA_SPEECH_LONG_INVOKE_URL")
        self.long_secret = os.getenv("CLOVA_SPEECH_LONG_SECRET_KEY")
        if not self.long_invoke_url or not self.long_secret:
            raise ValueError("CLOVA_SPEECH_LONG_* env vars not set.")
            
        # Short-form API credentials - Uses a DIFFERENT URL and SECRET from long-form
        self.short_invoke_url = os.getenv("CLOVA_SPEECH_SHORT_INVOKE_URL")
        self.short_secret = os.getenv("CLOVA_SPEECH_SHORT_SECRET_KEY")
        if not self.short_invoke_url or not self.short_secret:
            raise ValueError("CLOVA_SPEECH_SHORT_* env vars not set.")

    def recognize_long(self, audio_data: bytes, language="ko-KR") -> dict | None:
        """
        Recognizes speech from in-memory audio bytes using the /recognizer/upload endpoint (for long audio).
        This method uses a synchronous call and includes diarization.

        :param audio_data: The audio data in bytes (WAV format recommended).
        :param language: The language code for recognition.
        :return: The parsed API response as a dictionary, or None if an error occurs.
        """
        request_body = {
            "language": language,
            "completion": "sync",
            "wordAlignment": True,
            "diarization": { "enable": True, "speakerCountMin": 1, "speakerCountMax": 4 },
        }

        headers = {
            "Accept": "application/json;UTF-8",
            "X-CLOVASPEECH-API-KEY": self.long_secret,
        }

        files = {
            "media": ("media.wav", audio_data, "audio/wav"),
            "params": (None, json.dumps(request_body, ensure_ascii=False).encode("UTF-8"), "application/json"),
        }

        url = self.long_invoke_url + "/recognizer/upload"

        try:
            print(f"Sending long-form STT request to {url}...")
            response = requests.post(headers=headers, url=url, files=files, timeout=60)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            print(f"Clova Long API HTTP Error: {e}")
            if e.response:
                try:
                    error_details = e.response.json()
                    print(f"Error Details: {error_details}")
                except json.JSONDecodeError:
                    print(f"Could not parse error response. Status: {e.response.status_code}, Body: {e.response.text}")
            return None
        except Exception as e:
            print(f"An unexpected error occurred during Clova Long API call: {e}")
            return None

    def recognize_short(self, audio_data: bytes, language="Kor") -> str | None:
        """
        Recognizes speech using the Short-form API, based on the working curl command.
        This API uses its own URL and Secret Key.
        """
        headers = {
            "X-CLOVASPEECH-API-KEY": self.short_secret, # Uses short-form secret
            "Content-Type": "application/octet-stream",
        }
        # Correct path for short-form API is /stt
        url = self.short_invoke_url + f"?lang={language}"

        try:
            print(f"Sending Short-form STT request to {url}...")
            response = requests.post(url, headers=headers, data=audio_data, timeout=20)
            response.raise_for_status()
            result = response.json()
            print(f"Short API Response: {result}")
            return result.get("text")
        except Exception as e:
            print(f"Clova Short API HTTP Error: {e}")
            if hasattr(e, 'response') and e.response: print(f"Response Body: {e.response.text}")
            return None 