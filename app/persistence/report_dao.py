from .dao import PostgresDAO

class ReportDAO(PostgresDAO):
    """
    대화 마스터 테이블 (user_conversation_master):
    CREATE TABLE user_conversation_master (
        uid SERIAL PRIMARY KEY,
        user_uid INTEGER,
        topic VARCHAR(256),
        created_datetime TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    대화 상세 테이블 (user_conversation_detail):
    CREATE TABLE user_conversation_detail (
        uid SERIAL PRIMARY KEY,
        master_uid INTEGER REFERENCES user_conversation_master(uid) ON DELETE CASCADE,
        sentence TEXT,
        speaker VARCHAR(16),
        emotion_score JSONB,  -- {"positive":0.7, ...}
        emotion_text VARCHAR(32),
        audio_path VARCHAR(512),
        registered_datetime TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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

    def insert_conversation_detail(self, master_uid, sentence, speaker, emotion_score, emotion_text, audio_path=None):
        conn = self.get_connection()
        query = """
            INSERT INTO user_conversation_detail (master_uid, sentence, speaker, emotion_score, emotion_text, audio_path)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING uid
        """
        print(f"[쿼리] {query.strip()}\n[파라미터] master_uid={master_uid}, sentence={sentence}, speaker={speaker}, emotion_score={emotion_score}, emotion_text={emotion_text}, audio_path={audio_path}")
        with conn.cursor() as cur:
            cur.execute(query, (master_uid, sentence, speaker, emotion_score, emotion_text, audio_path))
            detail_uid = cur.fetchone()[0]
            conn.commit()
            return detail_uid

    def get_conversation_master_list(self, user_uid):
        conn = self.get_connection()
        query = """
            SELECT uid, topic, created_datetime
            FROM user_conversation_master
            WHERE user_uid = %s
            ORDER BY created_datetime DESC
        """
        with conn.cursor() as cur:
            cur.execute(query, (user_uid,))
            rows = cur.fetchall()
            result = []
            for row in rows:
                master_uid, topic, created_datetime = row
                result.append({
                    "master_uid": master_uid,
                    "topic": topic,
                    "created_datetime": str(created_datetime),
                })
            return result

    def get_conversation_details(self, master_uid):
        conn = self.get_connection()
        query = """
            SELECT uid, sentence, speaker, emotion_score, emotion_text, audio_path, registered_datetime
            FROM user_conversation_detail
            WHERE master_uid = %s
            ORDER BY uid ASC
        """
        with conn.cursor() as cur:
            cur.execute(query, (master_uid,))
            rows = cur.fetchall()
            result = []
            for row in rows:
                detail_uid, sentence, speaker, emotion_score, emotion_text, audio_path, registered_datetime = row
                result.append({
                    "detail_uid": detail_uid,
                    "sentence": sentence,
                    "speaker": speaker,
                    "emotion_score": emotion_score,
                    "emotion_text": emotion_text,
                    "audio_path": audio_path,
                    "registered_datetime": str(registered_datetime),
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