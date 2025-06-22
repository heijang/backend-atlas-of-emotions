import os
import sys

# 테스트 스크립트를 직접 실행할 수 있도록 프로젝트 루트를 Python 경로에 추가합니다.
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, project_root)

from app.providers.clova_speech_client import ClovaSpeechClient

def test_recognize_short():
    """
    ClovaSpeechClient의 recognize_short 메소드를 테스트합니다.
    이 스크립트를 직접 실행하면 테스트가 수행됩니다.
    (예: python test/providers/clova_speech_client_test.py)
    """
    print("--- Clova Speech Short API Test ---")

    # 1. 클라이언트 초기화
    try:
        client = ClovaSpeechClient()
        print("ClovaSpeechClient initialized successfully.")
    except ValueError as e:
        print(f"Client initialization failed: {e}")
        print("Please ensure your ENV/.env file is correctly configured with CLOVA_SPEECH_SHORT_* variables.")
        return

    # 2. 테스트할 오디오 파일 경로 정의
    audio_file_path = "storage/audio/wav_chunks/session_20250622_163110_129715_4925687504.wav"
    
    if not os.path.exists(audio_file_path):
        print(f"Error: Test audio file not found at '{audio_file_path}'")
        return
        
    print(f"Using test audio file: {audio_file_path}")

    # 3. 오디오 파일 읽기
    try:
        with open(audio_file_path, "rb") as f:
            audio_data = f.read()
        print(f"Successfully read {len(audio_data)} bytes from the audio file.")
    except IOError as e:
        print(f"Error reading audio file: {e}")
        return

    # 4. recognize_short 메소드 호출
    print("\nCalling recognize_short method...")
    result_text = client.recognize_short(audio_data)

    # 5. 결과 출력
    print("\n--- Test Result ---")
    if result_text is not None:
        print(f"  Transcription: '{result_text}'")
    else:
        print("  Transcription failed. Check the logs above for details.")
    print("--------------------")

if __name__ == "__main__":
    test_recognize_short() 