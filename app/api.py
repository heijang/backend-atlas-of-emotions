from fastapi import APIRouter

router = APIRouter()

@router.get("/report/{user_id}")
async def get_report(user_id: int):
    # 예시 데이터
    return {"user_id": user_id, "report": "감정 분석 결과"} 