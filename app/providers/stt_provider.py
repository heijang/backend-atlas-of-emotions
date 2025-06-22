from app.providers.google_stt_client import GoogleSTTProvider
from app.providers.clova_speech_client import ClovaSpeechClient

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
        """실시간 처리를 위해 Short API를 호출합니다."""
        return self.client.recognize_short(audio_bytes)

    def sync(self, audio_bytes: bytes) -> dict | None:
        """최종 분석을 위해 Long API를 호출합니다."""
        return self.client.recognize_long(audio_bytes)


# --- Provider 인스턴스를 반환하는 함수 ---
def get_streaming_stt_provider():
    """실시간(chunk) STT를 위한 Provider 인스턴스를 반환합니다."""
    # 현재는 Google STT를 사용. Clova Short API로 변경하려면 아래 주석을 해제.
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