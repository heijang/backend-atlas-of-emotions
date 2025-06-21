import requests
import json
import os
import time


class ClovaSpeechClient:
    """
    Naver Clova Speech API client using the multipart/form-data upload method.
    """

    def __init__(self):
        # 사용자가 수정한 .env 키 이름과 일치시킵니다.
        self.invoke_url = os.getenv("CLOVA_INVOKE_URL")
        self.secret = os.getenv("CLOVA_SECRET_KEY")
        if not self.invoke_url or not self.secret:
            raise ValueError(
                "Clova INVOKE_URL or SECRET_KEY is not configured in environment variables."
            )

    def recognize(self, audio_bytes: bytes, language="ko-KR"):
        """
        Recognizes speech from in-memory audio bytes using the /recognizer/upload endpoint.

        :param audio_bytes: The audio data in bytes (WAV format recommended).
        :param language: The language code for recognition.
        :return: The parsed API response as a dictionary.
        """
        # API 요청에 필요한 파라미터를 JSON 형식으로 구성합니다.
        # 'completion': 'sync'는 요청이 완료될 때까지 기다리는 동기 방식입니다.
        request_body = {
            "language": language,
            "completion": "sync",
            "wordAlignment": True,
            "diarization": {
                "enable": True,
                "speakerCountMin": 1,
                "speakerCountMax": 4,  # 최대 화자 수
            },
        }

        headers = {
            "Accept": "application/json;UTF-8",
            "X-CLOVASPEECH-API-KEY": self.secret,
        }

        # multipart/form-data 요청을 구성합니다.
        # 'media' 파트: 인메모리 오디오 바이트
        # 'params' 파트: 위에서 정의한 JSON 설정
        files = {
            "media": ("media.wav", audio_bytes, "audio/wav"),
            "params": (
                None,
                json.dumps(request_body, ensure_ascii=False).encode("UTF-8"),
                "application/json",
            ),
        }

        # 제공해주신 코드에 따라 올바른 엔드포인트로 URL을 구성합니다.
        url = self.invoke_url + "/recognizer/upload"

        try:
            print(f"Sending multipart/form-data request to {url}...")
            response = requests.post(
                headers=headers, url=url, files=files, timeout=45
            )  # Timeout 증가
            response.raise_for_status()

            response_data = response.json()
            print("Clova API response received successfully.")
            return response_data

        except requests.exceptions.HTTPError as e:
            print(f"Clova API HTTP Error: {e}")
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