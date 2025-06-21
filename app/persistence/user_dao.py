from .dao import PostgresDAO
import numpy as np

class UserDAO(PostgresDAO):
    """
    users 테이블 구조 예시:
    CREATE TABLE users (
        uid SERIAL PRIMARY KEY,
        user_id VARCHAR(64) UNIQUE,
        user_name VARCHAR(128),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    
    user_voice_embeddings 테이블 예시:
    CREATE TABLE user_voice_embeddings (
        uid SERIAL PRIMARY KEY,
        user_uid INTEGER UNIQUE,
        embedding BYTEA,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """
    def register_user(self, user_id: str, user_name: str):
        query = """
            INSERT INTO users (user_id, user_name, created_at)
            VALUES (%s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (user_id) DO UPDATE SET user_name = EXCLUDED.user_name
        """
        self.execute_query(query, (user_id, user_name))

    def get_user_by_id(self, user_id: str):
        query = """
            SELECT uid, user_id, user_name, created_at
            FROM users
            WHERE user_id = %s
        """
        result = self.execute_query(query, (user_id,))
        if result:
            uid, user_id, user_name, created_at = result[0]
            return {
                'uid': uid,
                'user_id': user_id,
                'user_name': user_name,
                'created_at': str(created_at)
            }
        return None

    def save_user_voice_embedding(self, user_uid: int, embedding: np.ndarray):
        query = """
            INSERT INTO user_voice_embeddings (user_uid, embedding, created_at)
            VALUES (%s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (user_uid) DO UPDATE SET embedding = EXCLUDED.embedding, created_at = CURRENT_TIMESTAMP
        """
        embedding_bytes = embedding.tobytes()
        self.execute_query(query, (user_uid, embedding_bytes))

    def get_user_voice_embedding(self, user_uid: int):
        query = """
            SELECT embedding FROM user_voice_embeddings WHERE user_uid = %s
        """
        result = self.execute_query(query, (user_uid,))
        if result:
            embedding_bytes = result[0][0]
            return np.frombuffer(embedding_bytes, dtype=np.float32)
        return None 