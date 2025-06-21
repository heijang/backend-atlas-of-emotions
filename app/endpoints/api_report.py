import json

from fastapi import APIRouter, Response

router = APIRouter()

@router.get('/api/v1/report/{conversation_uid}')
def get_report(conversation_uid: int):
    # 예시 데이터
    data = {"conversation_uid": conversation_uid, "report": "감정 분석 결과"}
    return Response(content=json.dumps(data, ensure_ascii=False), media_type='application/json')