from fastapi import APIRouter, WebSocket

router = APIRouter()

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    while True:
        data = await websocket.receive_text()
        # 처리 로직
        await websocket.send_text(f"Echo: {data}") 