import numpy as np
import torch
import librosa
from speechbrain.inference import EncoderClassifier

class VoiceEmbeddingService:
    _classifier = None

    def __init__(self):
        if VoiceEmbeddingService._classifier is None:
            try:
                # speechbrain/spkrec-ecapa-voxceleb 모델을 로드합니다.
                # savedir을 지정하여 모델 파일을 캐시할 수 있습니다.
                source = "speechbrain/spkrec-ecapa-voxceleb"
                savedir = "/tmp/spkrec-ecapa-voxceleb"
                VoiceEmbeddingService._classifier = EncoderClassifier.from_hparams(source=source, savedir=savedir)
                print("[음성 임베딩 서비스] 분류기 모델 로드 성공.")
            except Exception as e:
                print(f"[음성 임베딩 서비스] 분류기 모델 로드 실패: {e}")
                raise
        self.classifier = VoiceEmbeddingService._classifier

    def extract_voice_embedding(self, audio_path: str) -> np.ndarray | None:
        """
        오디오 파일 경로를 받아 voice embedding을 추출합니다.

        Args:
            audio_path (str): 오디오 파일의 경로.

        Returns:
            np.ndarray | None: 추출된 임베딩(numpy array) 또는 실패 시 None.
        """
        if self.classifier is None:
            print("[임베딩 추출] 오류: 분류기(classifier)가 초기화되지 않았습니다.")
            return None
        
        try:
            signal, fs = librosa.load(audio_path, sr=16000)
            
            # 음성 데이터가 너무 짧을 경우(0.5초 미만) 에러가 발생하므로 패딩 처리합니다.
            min_length = 8000 # 16000 * 0.5
            if len(signal) < min_length:
                signal = np.pad(signal, (0, min_length - len(signal)), 'constant')

            # speechbrain 모델을 사용하여 임베딩을 추출합니다.
            embeddings = self.classifier.encode_batch(torch.tensor(signal).unsqueeze(0))
            embedding_np = embeddings.squeeze().cpu().numpy().astype(np.float32)
            
            return embedding_np
        except Exception as e:
            print(f"[임베딩 추출] 오류 발생: {e} (오디오 파일: {audio_path})")
            return None

# 싱글턴 인스턴스
# 애플리케이션 전체에서 하나의 VoiceEmbeddingService 인스턴스만 사용하도록 하여
# 모델을 한번만 로드하게 만듭니다.
voice_embedding_service = VoiceEmbeddingService()