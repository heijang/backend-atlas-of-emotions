from app.providers.google_stt_client import GoogleSTTProvider
from app.providers.clova_speech_client import ClovaSpeechClient
import io
import wave

# --- Provider 인스턴스를 싱글턴으로 관리 ---
_google_stt_provider = None
_clova_stt_provider = None

# --- Adapter 클래스 정의 ---
class ClovaSTTAdapter:
    """
    ClovaSpeechClient를 기존 Provider 인터페이스에 맞게 조정하는 어댑터 클래스입니다.
    """
    def __init__(self):
        self.client = ClovaSpeechClient()

    def streaming(self, audio_bytes: bytes) -> str | None:
        """실시간 처리를 위해 Short API를 호출합니다.
        Raw PCM 데이터를 in-memory WAV로 변환하여 전달합니다.
        """
        with io.BytesIO() as wav_io:
            with wave.open(wav_io, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)      # 16-bit
                wf.setframerate(16000)  # 16kHz
                wf.writeframes(audio_bytes)
            wav_bytes = wav_io.getvalue()
            
        return self.client.recognize_short(wav_bytes)

    def sync(self, audio_bytes: bytes) -> dict | None:
        """최종 분석을 위해 Long API를 호출합니다."""
        return self.client.recognize_long(audio_bytes)


# --- Provider 인스턴스를 반환하는 함수 ---
def get_streaming_stt_provider():
    """실시간(chunk) STT를 위한 Provider 인스턴스를 반환합니다."""
    # Clova Short API를 사용하도록 변경합니다.
    global _google_stt_provider
    if _google_stt_provider is None:
        _google_stt_provider = GoogleSTTProvider()
    return _google_stt_provider
    # global _clova_stt_provider
    # if _clova_stt_provider is None:
    #     _clova_stt_provider = ClovaSTTAdapter()
    # return _clova_stt_provider


def get_sync_stt_provider():
    """최종(sync) STT를 위한 Provider 인스턴스를 반환합니다."""
    global _clova_stt_provider
    if _clova_stt_provider is None:
        _clova_stt_provider = ClovaSTTAdapter()
    return _clova_stt_provider 