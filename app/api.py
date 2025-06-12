from fastapi import APIRouter, WebSocket, UploadFile, File
from starlette.websockets import WebSocketDisconnect
import os
from app.audio_utils import extract_and_save_embedding, get_storage_audio_path

router = APIRouter()

@router.get("/report/{user_id}")
async def get_report(user_id: int):
    # 예시 데이터
    return {"user_id": user_id, "report": "감정 분석 결과"}

@router.post("/embed-audio/")
async def embed_audio(file: UploadFile = File(...)):
    upload_dir = get_storage_audio_path("uploads")
    os.makedirs(upload_dir, exist_ok=True)
    file_path = os.path.join(upload_dir, file.filename)
    with open(file_path, "wb") as f:
        f.write(await file.read())
    embedding_path = extract_and_save_embedding(file_path)
    return {"embedding_file": embedding_path}

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