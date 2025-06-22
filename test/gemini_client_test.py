import sys
from app.providers.gemini_client import analyze_emotions
import numpy as np
import librosa
import os

# 테스트용 파일 경로
audio_path = "storage/audio/wav_chunks/session_20250616_163640_382207_4360721872.wav"
text = "이 주임 어제 내가 요청한 수정 사항 왜 반영 안 된 거야? 아침 회의 자료에서 빠졌던데, 밤에 다 반영해서 드라이버에 올리고 톡방에도 남겼습니다. 그럼 왜 내가 그걸 못 본 거지?"

# 오디오 파일 로드 (16kHz, mono)
audio_array, sr = librosa.load(audio_path, sr=16000, mono=True)

# 감정 분석 실행
result = analyze_emotions(text, audio_array)

# 결과 출력 (가독성 있게)
import pprint
pp = pprint.PrettyPrinter(indent=2, width=120)
print("=== 감정 분석 결과 ===")
pp.pprint(result) 