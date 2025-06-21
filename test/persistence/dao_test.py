"""
DAO 테스트 스크립트 사용법

- DB 연결 테스트:
    python -m app.persistence.dao_test connect

- 감정분석 대화 리스트 조회:
    python -m app.persistence.dao_test get_user_conversations_with_emotions "1"
"""
import sys
from ...app.persistence.report_dao import ReportDAO
from ...app.persistence.user_dao import UserDAO

def test_connect():
    dao = ReportDAO()
    try:
        dao.connect()
        print("DB 연결 성공!")
    except Exception as e:
        print(f"DB 연결 실패: {e}")
    finally:
        dao.close()

# get_user_conversations_with_emotions 함수는 report_dao.py에서 제거되었으므로 주석 처리
# def test_get_user_conversations_with_emotions(user_id):
#     dao = ReportDAO()
#     try:
#         data = dao.get_user_conversations_with_emotions(user_id)
#         from pprint import pprint
#         pprint(data)
#     except Exception as e:
#         print(f"쿼리 실패: {e}")
#     finally:
#         dao.close()

def test_register_user(user_id, user_name):
    dao = UserDAO()
    try:
        dao.register_user(user_id, user_name)
        print(f"User registered: {user_id}, {user_name}")
    except Exception as e:
        print(f"User registration failed: {e}")
    finally:
        dao.close()

def test_login_user(user_id):
    dao = UserDAO()
    try:
        user = dao.get_user_by_id(user_id)
        if user:
            print(f"User found: {user}")
        else:
            print("User not found")
    except Exception as e:
        print(f"Login failed: {e}")
    finally:
        dao.close()

def test_insert_conversation_master(user_id, topic=None):
    dao = ReportDAO()
    try:
        master_id = dao.insert_conversation_master(user_id, topic)
        print(f"Inserted master: id={master_id}")
    except Exception as e:
        print(f"Insert master failed: {e}")
    finally:
        dao.close()

def test_update_master_audio_path(master_id, audio_path):
    dao = ReportDAO()
    try:
        dao.update_master_audio_path(master_id, audio_path)
        print(f"Updated master audio path: master_id={master_id}, audio_path={audio_path}")
    except Exception as e:
        print(f"Update master audio path failed: {e}")
    finally:
        dao.close()

def test_insert_conversation_detail(master_id, sentence, speaker, emotion_result, dominant_emotion, start_ms, end_ms):
    dao = ReportDAO()
    try:
        detail_id = dao.insert_conversation_detail(master_id, sentence, speaker, emotion_result, dominant_emotion, start_ms, end_ms)
        print(f"Inserted detail: id={detail_id}")
    except Exception as e:
        print(f"Insert detail failed: {e}")
    finally:
        dao.close()

def test_get_conversation_master_list(user_id):
    dao = ReportDAO()
    try:
        data = dao.get_conversation_master_list(user_id)
        from pprint import pprint
        pprint(data)
    except Exception as e:
        print(f"쿼리 실패: {e}")
    finally:
        dao.close()

def test_get_conversation_details(master_id):
    dao = ReportDAO()
    try:
        data = dao.get_conversation_details(master_id)
        from pprint import pprint
        pprint(data)
    except Exception as e:
        print(f"쿼리 실패: {e}")
    finally:
        dao.close()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise ValueError("인자가 맞지 않습니다.")
    cmd = sys.argv[1]
    if cmd == "connect":
        test_connect()
    # elif cmd == "get_user_conversations_with_emotions": # report_dao.py에서 제거되었으므로 주석 처리
    #     if len(sys.argv) < 3:
    #         raise ValueError("인자가 맞지 않습니다.")
    #     user_id = sys.argv[2]
    #     test_get_user_conversations_with_emotions(user_id)
    elif cmd == "get_conversation_master_list":
        if len(sys.argv) < 3:
            raise ValueError("인자가 맞지 않습니다.")
        user_id = sys.argv[2]
        test_get_conversation_master_list(user_id)
    elif cmd == "get_conversation_details":
        if len(sys.argv) < 3:
            raise ValueError("인자가 맞지 않습니다.")
        master_id = sys.argv[2]
        test_get_conversation_details(master_id)
    elif cmd == "update_master_audio_path":
        if len(sys.argv) < 4:
            raise ValueError("인자가 맞지 않습니다.")
        master_id = int(sys.argv[2])
        audio_path = sys.argv[3]
        test_update_master_audio_path(master_id, audio_path)
    elif cmd == "insert_conversation_detail":
        if len(sys.argv) < 9:
            raise ValueError("인자가 맞지 않습니다.")
        master_id = int(sys.argv[2])
        sentence = sys.argv[3]
        speaker = sys.argv[4]
        emotion_result = sys.argv[5] # JSON string
        dominant_emotion = sys.argv[6]
        start_ms = int(sys.argv[7])
        end_ms = int(sys.argv[8])
        test_insert_conversation_detail(master_id, sentence, speaker, emotion_result, dominant_emotion, start_ms, end_ms)
    elif cmd == "register_user":
        if len(sys.argv) < 4:
            raise ValueError("인자가 맞지 않습니다.")
        user_id = sys.argv[2]
        user_name = sys.argv[3]
        test_register_user(user_id, user_name)
    elif cmd == "login_user":
        if len(sys.argv) < 3:
            raise ValueError("인자가 맞지 않습니다.")
        user_id = sys.argv[2]
        test_login_user(user_id)
    else:
        raise ValueError("인자가 맞지 않습니다.") 