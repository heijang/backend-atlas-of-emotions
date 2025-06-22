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
    Naver Clova Speech API client using the multipart/form-data upload method.
    This implementation is based on the user-provided code.
    """

    def __init__(self):
        self.invoke_url = os.getenv("CLOVA_INVOKE_URL")
        self.secret = os.getenv("CLOVA_SECRET_KEY")
        if not self.invoke_url or not self.secret:
            raise ValueError(
                "Clova INVOKE_URL or SECRET_KEY is not configured in environment variables."
            )

    def recognize(self, audio_data: bytes, language="ko-KR") -> dict | None:
        """
        Recognizes speech from in-memory audio bytes using the /recognizer/upload endpoint.
        This method uses a synchronous call and includes diarization.

        :param audio_data: The audio data in bytes (WAV format recommended).
        :param language: The language code for recognition.
        :return: The parsed API response as a dictionary, or None if an error occurs.
        """
        request_body = {
            "language": language,
            "completion": "sync",
            "wordAlignment": True,
            "diarization": {
                "enable": True,
                "speakerCountMin": 1,
                "speakerCountMax": 4,
            },
        }

        headers = {
            "Accept": "application/json;UTF-8",
            "X-CLOVASPEECH-API-KEY": self.secret,
        }

        files = {
            "media": ("media.wav", audio_data, "audio/wav"),
            "params": (
                None,
                json.dumps(request_body, ensure_ascii=False).encode("UTF-8"),
                "application/json",
            ),
        }

        url = self.invoke_url + "/recognizer/upload"

        try:
            print(f"Sending multipart/form-data request to {url}...")
            response = requests.post(
                headers=headers, url=url, files=files, timeout=60
            )
            response.raise_for_status()

            response_data = response.json()
            print("Clova API response received successfully.")
            return response_data

        except requests.exceptions.HTTPError as e:
            print(f"Clova API HTTP Error: {e}")
            if e.response:
                try:
                    error_details = e.response.json()
                    print(f"Error Details: {error_details}")
                except json.JSONDecodeError:
                    print(
                        f"Could not parse error response. Status: {e.response.status_code}, Body: {e.response.text}"
                    )
            return None
        except Exception as e:
            print(f"An unexpected error occurred during Clova API call: {e}")
            return None

    def get_transcribed_text(self, audio_data: bytes, language="ko-KR") -> str | None:
        """
        A wrapper around recognize() to extract only the final transcribed text.
        """
        result = self.recognize(audio_data, language)
        if result:
            return result.get("text")
        return None


class ClovaSTTProvider:
    def __init__(self):
        self.client = ClovaSpeechClient()

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