from fastapi import APIRouter, WebSocket
from starlette.websockets import WebSocketDisconnect

router = APIRouter()

@router.get("/report/{user_id}")
async def get_report(user_id: int):
    # 예시 데이터
    return {"user_id": user_id, "report": "감정 분석 결과"}

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print(f"🟢 연결됨: {websocket.client}")
    try:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                print("🔌 클라이언트 연결 해제")
                break
            elif message["type"] == "websocket.receive":
                if "bytes" in message and message["bytes"] is not None:
                    # 바이너리 데이터 처리
                    data = message["bytes"]
                    # ... (이전 로직)
                elif "text" in message and message["text"] is not None:
                    # 텍스트 데이터 처리 (필요시)
                    print("텍스트 데이터 수신:", message["text"])
    except WebSocketDisconnect:
        print("🔌 클라이언트 연결 해제")
    except Exception as e:
        print(f"❌ 에러: {e}")
        await websocket.close() 