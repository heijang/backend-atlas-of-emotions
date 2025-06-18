import numpy as np
from app.audio_utils import extract_voice_embedding, cosine_similarity
from app.persistence.user_dao import UserDAO

# Helper: user_id(str) -> user_uid(int)
def get_user_uid_by_user_id(user_id: str) -> int:
    dao = UserDAO()
    try:
        user = dao.get_user_by_id(user_id)
        if user:
            return user['uid']
    finally:
        dao.close()
    return None

# 1. 음성 파일을 받아서 임베딩 처리 후 결과 반환
def extract_voice_embedding_from_file(audio_path: str) -> np.ndarray:
    return extract_voice_embedding(audio_path)

# 2. 유저 음성 파일을 받아서 (1) 번 처리 후 결과를 DB 저장
def save_user_voice_embedding_to_db(user_uid: int, audio_path: str):
    embedding = extract_voice_embedding(audio_path)
    dao = UserDAO()
    try:
        dao.save_user_voice_embedding(user_uid, embedding)
    finally:
        dao.close()
    return embedding

# 3. 유저 정보로 (1) 번 처리로 저장된 DB 결과를 조회해서 메모리 저장
def load_user_voice_embedding_to_memory(user_key) -> np.ndarray:
    """
    user_key: user_uid(int) 또는 user_id(str) 모두 허용
    내부적으로 user_uid(int)로 변환 후 임베딩 반환
    """
    user_uid = user_key
    if isinstance(user_key, str):
        user_uid = get_user_uid_by_user_id(user_key)
    if user_uid is None:
        print(f"load_user_voice_embedding_to_memory: user_uid를 찾을 수 없음 (입력값: {user_key})")
        return None
    dao = UserDAO()
    try:
        embedding = dao.get_user_voice_embedding(user_uid)
    except Exception as e:
        print(f"load_user_voice_embedding_to_memory error: {e}")
    finally:
        dao.close()
    return embedding

# 4. 음성 파일을 받아서 메모리에 적재 된 유저정보와 비교해서 동일한지 판단
def compare_voice_with_memory(audio_path: str, user_embedding: np.ndarray, threshold: float = 0.75) -> bool:
    print(f"[compare_voice_with_memory] audio_path={audio_path}, user_embedding shape={getattr(user_embedding, 'shape', None)}")
    # 실제로는 segment별로 잘라진 오디오 파일을 써야 정확함 (현재는 전체 파일 사용)
    test_embedding = extract_voice_embedding(audio_path)
    similarity = cosine_similarity(test_embedding, user_embedding)
    return similarity >= threshold, similarity 