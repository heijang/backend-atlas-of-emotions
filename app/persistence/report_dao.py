from .dao import PostgresDAO

class ReportDAO(PostgresDAO):
    """
    대화 마스터 테이블 (user_conversation_master):
    CREATE TABLE user_conversation_master (
        uid SERIAL PRIMARY KEY,
        user_uid INTEGER,
        topic VARCHAR(256),
        audio_path VARCHAR(512),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    대화 상세 테이블 (user_conversation_detail):
    CREATE TABLE user_conversation_detail (
        uid SERIAL PRIMARY KEY,
        master_uid INTEGER REFERENCES user_conversation_master(uid) ON DELETE CASCADE,
        sentence TEXT,
        speaker VARCHAR(16),
        emotion_result JSONB,  -- 전체 감정분석 결과
        dominant_emotion VARCHAR(32),  -- 가장 높은 감정 key
        start_ms INTEGER,
        end_ms INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """
    def insert_conversation_master(self, user_uid, topic=None):
        conn = self.get_connection()
        query = """
            INSERT INTO user_conversation_master (user_uid, topic)
            VALUES (%s, %s)
            RETURNING uid
        """
        with conn.cursor() as cur:
            cur.execute(query, (user_uid, topic))
            master_uid = cur.fetchone()[0]
            conn.commit()
            return master_uid

    def update_master_audio_path(self, master_uid, audio_path):
        conn = self.get_connection()
        query = """
            UPDATE user_conversation_master
            SET audio_path = %s
            WHERE uid = %s
        """
        with conn.cursor() as cur:
            cur.execute(query, (audio_path, master_uid))
            conn.commit()

    def insert_conversation_detail(self, master_uid, sentence, speaker, emotion_result, dominant_emotion, start_ms, end_ms):
        conn = self.get_connection()
        query = """
            INSERT INTO user_conversation_detail (master_uid, sentence, speaker, emotion_result, dominant_emotion, start_ms, end_ms)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING uid
        """
        print(f"[쿼리] {query.strip()}\n[파라미터] master_uid={master_uid}, sentence={sentence}, speaker={speaker}, emotion_result={emotion_result}, dominant_emotion={dominant_emotion}, start_ms={start_ms}, end_ms={end_ms}")
        with conn.cursor() as cur:
            cur.execute(query, (master_uid, sentence, speaker, emotion_result, dominant_emotion, start_ms, end_ms))
            detail_uid = cur.fetchone()[0]
            conn.commit()
            return detail_uid

    def get_conversation_master_list(self, user_uid):
        conn = self.get_connection()
        query = """
            SELECT uid, topic, created_at
            FROM user_conversation_master
            WHERE user_uid = %s
            ORDER BY created_at DESC
        """
        with conn.cursor() as cur:
            cur.execute(query, (user_uid,))
            rows = cur.fetchall()
            result = []
            for row in rows:
                master_uid, topic, created_at = row
                result.append({
                    "master_uid": master_uid,
                    "topic": topic,
                    "created_at": str(created_at),
                })
            return result

    def get_conversation_details(self, master_uid):
        conn = self.get_connection()
        query = """
            SELECT d.uid, d.sentence, d.speaker, d.emotion_result, d.dominant_emotion, 
                   d.start_ms, d.end_ms, d.created_at,
                   m.audio_path
            FROM user_conversation_detail d
            JOIN user_conversation_master m ON d.master_uid = m.uid
            WHERE d.master_uid = %s
            ORDER BY d.uid ASC
        """
        with conn.cursor() as cur:
            cur.execute(query, (master_uid,))
            rows = cur.fetchall()
            result = []
            for row in rows:
                detail_uid, sentence, speaker, emotion_result, dominant_emotion, start_ms, end_ms, created_at, audio_path = row
                result.append({
                    "detail_uid": detail_uid,
                    "sentence": sentence,
                    "speaker": speaker,
                    "emotion_result": emotion_result,
                    "dominant_emotion": dominant_emotion,
                    "start_ms": start_ms,
                    "end_ms": end_ms,
                    "audio_path": audio_path,
                    "created_at": str(created_at),
                })
            return result

if __name__ == "__main__":
    dao = ReportDAO()
    try:
        user_uid = input("userUid 입력: ")
        data = dao.get_conversation_master_list(user_uid)
        from pprint import pprint
        pprint(data)
    except Exception as e:
        print(f"쿼리 실패: {e}")
    finally:
        dao.close() 