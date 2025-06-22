import numpy as np
from app.services.voice_service import voice_embedding_service
from app.utils.audio_utils import cosine_similarity
from app.dao.user_dao import UserDAO


class UserVoiceService:
    def __init__(self):
        self.user_dao = UserDAO()

    def register_user_voice(self, user_uid: int, audio_path: str) -> np.ndarray:
        """사용자의 음성 파일을 등록하고 임베딩을 반환합니다."""
        embedding = voice_embedding_service.extract_voice_embedding(audio_path)
        if embedding is not None:
            self.user_dao.save_user_voice_embedding(user_uid, embedding)
        return embedding

    def get_user_voice_embedding(self, user_uid: int) -> np.ndarray:
        """사용자의 음성 임베딩을 DB에서 조회합니다."""
        return self.user_dao.get_user_voice_embedding(user_uid)

    def compare_voice(self, audio_path: str, user_embedding: np.ndarray, threshold: float = 0.75) -> tuple[bool, float]:
        """입력된 음성과 기존 임베딩을 비교하여 유사도와 동일인 여부를 반환합니다."""
        if user_embedding is None:
            return False, 0.0
            
        test_embedding = voice_embedding_service.extract_voice_embedding(audio_path)
        if test_embedding is None:
            return False, 0.0

        similarity = cosine_similarity(test_embedding, user_embedding)
        is_same = similarity >= threshold
        return is_same, similarity

user_voice_service = UserVoiceService() 