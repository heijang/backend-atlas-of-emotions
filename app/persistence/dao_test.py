"""
DAO 테스트 스크립트 사용법

- DB 연결 테스트:
    python -m app.persistence.dao_test connect

- 감정분석 대화 리스트 조회:
    python -m app.persistence.dao_test get_user_conversations_with_emotions "1"
"""
import sys
from .report_dao import ReportDAO

def test_connect():
    dao = ReportDAO()
    try:
        dao.connect()
        print("DB 연결 성공!")
    except Exception as e:
        print(f"DB 연결 실패: {e}")
    finally:
        dao.close()

def test_get_user_conversations_with_emotions(user_id):
    dao = ReportDAO()
    try:
        data = dao.get_user_conversations_with_emotions(user_id)
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
    elif cmd == "get_user_conversations_with_emotions":
        if len(sys.argv) < 3:
            raise ValueError("인자가 맞지 않습니다.")
        user_id = sys.argv[2]
        test_get_user_conversations_with_emotions(user_id)
    else:
        raise ValueError("인자가 맞지 않습니다.") 