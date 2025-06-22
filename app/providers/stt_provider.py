from app.providers.google_stt_client import GoogleSTTProvider
from app.providers.clova_speech_client import ClovaSTTProvider

# chunk 단위 STT는 구글, 최종 STT는 클로바를 사용하도록 provider 분리
def get_streaming_stt_provider():
    return GoogleSTTProvider()

def get_sync_stt_provider():
    return ClovaSTTProvider() 