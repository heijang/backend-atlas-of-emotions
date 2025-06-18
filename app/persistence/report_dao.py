from .dao import PostgresDAO

class ReportDAO(PostgresDAO):
    """
    예시 테이블 구조 (user_conversations):
    CREATE TABLE user_conversations (
        id SERIAL PRIMARY KEY,
        user_id VARCHAR(64),
        sentence TEXT,
        speaker VARCHAR(16),
        emotion_score JSONB,  -- {"positive":0.7, "negative":0.2, ...}
        emotion_text VARCHAR(32),  -- 예: '긍정', '부정', '중립' 등
        registered_datetime TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """
    def get_user_conversations_with_emotions(self, user_id):
        conn = self.get_connection()
        query = """
            SELECT sentence, speaker, emotion_score, emotion_text, registered_datetime
            FROM user_conversations
            WHERE user_id = %s
            ORDER BY id ASC
        """
        with conn.cursor() as cur:
            cur.execute(query, (user_id,))
            rows = cur.fetchall()
            # 컬럼: sentence, speaker, emotion_score, emotion_text, registered_datetime
            result = []
            for row in rows:
                sentence, speaker, emotion_score, emotion_text, registered_datetime = row
                result.append({
                    "sentence": sentence,
                    "speaker": speaker,
                    "emotion_score": emotion_score,
                    "emotion_text": emotion_text,
                    "registered_datetime": str(registered_datetime),
                })
            return result

if __name__ == "__main__":
    dao = ReportDAO()
    try:
        user_id = input("userId 입력: ")
        data = dao.get_user_conversations_with_emotions(user_id)
        from pprint import pprint
        pprint(data)
    except Exception as e:
        print(f"쿼리 실패: {e}")
    finally:
        dao.close() 